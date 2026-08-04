"""Privacy-safe latency telemetry for provider-backed model calls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from math import ceil
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler


LOGGER = logging.getLogger("backend.llm.telemetry")
T = TypeVar("T")


@dataclass(slots=True)
class ModelLatencyTelemetry:
    """One content-free measurement for a provider-backed model operation."""

    workflow: str
    run_id: str
    provider: str
    model: str
    operation: str
    attempt: str
    measured_at: str
    status: str = "success"
    end_to_end_ms: float | None = None
    provider_request_ms: float | None = None
    framework_overhead_ms: float | None = None
    time_to_first_token_ms: float | None = None
    mean_inter_token_latency_ms: float | None = None
    p95_inter_token_latency_ms: float | None = None
    streamed_token_events: int = 0
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    end_to_end_output_tokens_per_second: float | None = None
    streamed_output_tokens_per_second: float | None = None
    provider_queue_ms: float | None = None
    provider_prefill_ms: float | None = None
    provider_decode_ms: float | None = None
    provider_timing_available: bool = False
    streaming_timing_available: bool = False
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe telemetry record."""

        return asdict(self)


class ModelLatencyCallback(BaseCallbackHandler):
    """Collect LangChain callback timings and response usage metadata."""

    def __init__(self) -> None:
        self.provider_started_at: float | None = None
        self.provider_finished_at: float | None = None
        self.token_event_times: list[float] = []
        self.input_tokens: int | None = None
        self.cached_input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.total_tokens: int | None = None
        self.provider_queue_ms: float | None = None
        self.provider_prefill_ms: float | None = None
        self.provider_decode_ms: float | None = None

    def on_llm_start(self, *_: Any, **__: Any) -> None:
        self._mark_provider_start()

    def on_chat_model_start(self, *_: Any, **__: Any) -> None:
        self._mark_provider_start()

    def on_llm_new_token(self, _: str, **__: Any) -> None:
        self.token_event_times.append(perf_counter())

    def on_llm_end(self, response: Any, **__: Any) -> None:
        self.provider_finished_at = perf_counter()
        usage, response_metadata = _extract_langchain_response_metadata(response)
        self._merge_usage(usage)
        self._merge_provider_timings(response_metadata)

    def on_llm_error(self, _: BaseException, **__: Any) -> None:
        self.provider_finished_at = perf_counter()

    def _mark_provider_start(self) -> None:
        if self.provider_started_at is None:
            self.provider_started_at = perf_counter()

    def _merge_usage(self, usage: Mapping[str, Any]) -> None:
        self.input_tokens = _first_int(
            usage,
            "input_tokens",
            "prompt_tokens",
            fallback=self.input_tokens,
        )
        self.output_tokens = _first_int(
            usage,
            "output_tokens",
            "completion_tokens",
            fallback=self.output_tokens,
        )
        self.total_tokens = _first_int(
            usage,
            "total_tokens",
            fallback=self.total_tokens,
        )
        input_details = _as_mapping(
            usage.get("input_token_details") or usage.get("prompt_tokens_details")
        )
        self.cached_input_tokens = _first_int(
            input_details,
            "cache_read",
            "cached_tokens",
            fallback=self.cached_input_tokens,
        )

    def _merge_provider_timings(self, metadata: Mapping[str, Any]) -> None:
        timing_sources = [
            metadata,
            _as_mapping(metadata.get("timings")),
            _as_mapping(metadata.get("metrics")),
        ]
        self.provider_queue_ms = _first_timing_ms(
            timing_sources,
            "queue_time_ms",
            "queue_ms",
            "queue_time",
        )
        self.provider_prefill_ms = _first_timing_ms(
            timing_sources,
            "prefill_time_ms",
            "prompt_time_ms",
            "prefill_ms",
            "prompt_time",
        )
        self.provider_decode_ms = _first_timing_ms(
            timing_sources,
            "decode_time_ms",
            "completion_time_ms",
            "decode_ms",
            "completion_time",
        )


def invoke_with_model_telemetry(
    runnable: Any,
    payload: Any,
    *,
    workflow: str,
    provider: str,
    model: str,
    run_id: str | None = None,
    attempt: str = "primary",
) -> tuple[Any, dict[str, Any]]:
    """Invoke a LangChain runnable and emit one content-free latency record."""

    callback = ModelLatencyCallback()
    telemetry = _new_telemetry(
        workflow=workflow,
        provider=provider,
        model=model,
        operation="chat",
        run_id=run_id,
        attempt=attempt,
    )
    started_at = perf_counter()
    configured_runnable = runnable
    with_config = getattr(runnable, "with_config", None)
    if callable(with_config):
        configured_runnable = with_config(
            {
                "callbacks": [callback],
                "metadata": {
                    "workflow": workflow,
                    "model_run_id": telemetry.run_id,
                    "model_attempt": attempt,
                },
                "run_name": workflow,
            }
        )

    try:
        result = configured_runnable.invoke(payload)
    except Exception as exc:
        _finalize_telemetry(
            telemetry,
            callback=callback,
            started_at=started_at,
            error=exc,
        )
        _emit_telemetry(telemetry)
        raise

    _finalize_telemetry(
        telemetry,
        callback=callback,
        started_at=started_at,
    )
    _emit_telemetry(telemetry)
    return result, telemetry.to_dict()


def invoke_provider_with_telemetry(
    operation: Callable[[], T],
    *,
    workflow: str,
    provider: str,
    model: str,
    run_id: str | None = None,
    attempt: str = "primary",
    usage_extractor: Callable[[T], Mapping[str, Any]] | None = None,
) -> tuple[T, dict[str, Any]]:
    """Measure a direct provider SDK operation such as an embedding request."""

    telemetry = _new_telemetry(
        workflow=workflow,
        provider=provider,
        model=model,
        operation="embedding",
        run_id=run_id,
        attempt=attempt,
    )
    started_at = perf_counter()
    try:
        result = operation()
    except Exception as exc:
        telemetry.status = "error"
        telemetry.error_type = exc.__class__.__name__
        telemetry.end_to_end_ms = _milliseconds(perf_counter() - started_at)
        telemetry.provider_request_ms = telemetry.end_to_end_ms
        _emit_telemetry(telemetry)
        raise

    telemetry.end_to_end_ms = _milliseconds(perf_counter() - started_at)
    telemetry.provider_request_ms = telemetry.end_to_end_ms
    if usage_extractor is not None:
        usage = usage_extractor(result)
        telemetry.input_tokens = _first_int(usage, "input_tokens", "prompt_tokens")
        telemetry.output_tokens = _first_int(
            usage,
            "output_tokens",
            "completion_tokens",
        )
        telemetry.total_tokens = _first_int(usage, "total_tokens")
    _derive_throughput(telemetry)
    _emit_telemetry(telemetry)
    return result, telemetry.to_dict()


def _new_telemetry(
    *,
    workflow: str,
    provider: str,
    model: str,
    operation: str,
    run_id: str | None,
    attempt: str,
) -> ModelLatencyTelemetry:
    return ModelLatencyTelemetry(
        workflow=workflow,
        run_id=run_id or str(uuid4()),
        provider=provider,
        model=model,
        operation=operation,
        attempt=attempt,
        measured_at=datetime.now(timezone.utc).isoformat(),
    )


def _finalize_telemetry(
    telemetry: ModelLatencyTelemetry,
    *,
    callback: ModelLatencyCallback,
    started_at: float,
    error: Exception | None = None,
) -> None:
    finished_at = perf_counter()
    telemetry.end_to_end_ms = _milliseconds(finished_at - started_at)
    if callback.provider_started_at is not None:
        provider_finished_at = callback.provider_finished_at or finished_at
        telemetry.provider_request_ms = _milliseconds(
            provider_finished_at - callback.provider_started_at
        )
        telemetry.framework_overhead_ms = max(
            0.0,
            round(telemetry.end_to_end_ms - telemetry.provider_request_ms, 3),
        )
    telemetry.input_tokens = callback.input_tokens
    telemetry.cached_input_tokens = callback.cached_input_tokens
    telemetry.output_tokens = callback.output_tokens
    telemetry.total_tokens = callback.total_tokens
    telemetry.provider_queue_ms = callback.provider_queue_ms
    telemetry.provider_prefill_ms = callback.provider_prefill_ms
    telemetry.provider_decode_ms = callback.provider_decode_ms
    telemetry.provider_timing_available = any(
        value is not None
        for value in (
            telemetry.provider_queue_ms,
            telemetry.provider_prefill_ms,
            telemetry.provider_decode_ms,
        )
    )

    token_times = callback.token_event_times
    telemetry.streamed_token_events = len(token_times)
    if token_times and callback.provider_started_at is not None:
        telemetry.streaming_timing_available = True
        telemetry.time_to_first_token_ms = _milliseconds(
            token_times[0] - callback.provider_started_at
        )
        intervals = [
            later - earlier
            for earlier, later in zip(token_times, token_times[1:], strict=False)
        ]
        if intervals:
            interval_values = sorted(_milliseconds(value) for value in intervals)
            telemetry.mean_inter_token_latency_ms = round(
                sum(interval_values) / len(interval_values),
                3,
            )
            telemetry.p95_inter_token_latency_ms = interval_values[
                max(0, ceil(len(interval_values) * 0.95) - 1)
            ]
        stream_finished_at = callback.provider_finished_at or finished_at
        streamed_seconds = stream_finished_at - token_times[0]
        if streamed_seconds > 0:
            token_count = telemetry.output_tokens or len(token_times)
            telemetry.streamed_output_tokens_per_second = round(
                token_count / streamed_seconds,
                3,
            )

    if error is not None:
        telemetry.status = "error"
        telemetry.error_type = error.__class__.__name__
    _derive_throughput(telemetry)


def _derive_throughput(telemetry: ModelLatencyTelemetry) -> None:
    if (
        telemetry.output_tokens is not None
        and telemetry.end_to_end_ms is not None
        and telemetry.end_to_end_ms > 0
    ):
        telemetry.end_to_end_output_tokens_per_second = round(
            telemetry.output_tokens / (telemetry.end_to_end_ms / 1000),
            3,
        )


def _extract_langchain_response_metadata(
    response: Any,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    usage: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    llm_output = _as_mapping(getattr(response, "llm_output", None))
    usage.update(_as_mapping(llm_output.get("token_usage")))
    metadata.update(llm_output)

    for generation_group in getattr(response, "generations", []) or []:
        for generation in generation_group or []:
            message = getattr(generation, "message", None)
            usage.update(_as_mapping(getattr(message, "usage_metadata", None)))
            metadata.update(_as_mapping(getattr(message, "response_metadata", None)))
    return usage, metadata


def _first_int(
    values: Mapping[str, Any],
    *keys: str,
    fallback: int | None = None,
) -> int | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return fallback


def _first_timing_ms(
    sources: list[Mapping[str, Any]],
    *keys: str,
) -> float | None:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            numeric_value = float(value)
            if not key.endswith("_ms") and numeric_value < 100:
                numeric_value *= 1000
            return round(numeric_value, 3)
    return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _milliseconds(seconds: float) -> float:
    return round(max(0.0, seconds) * 1000, 3)


def _emit_telemetry(telemetry: ModelLatencyTelemetry) -> None:
    LOGGER.info(
        "model_latency %s",
        json.dumps(telemetry.to_dict(), sort_keys=True, separators=(",", ":")),
    )


__all__ = [
    "ModelLatencyCallback",
    "ModelLatencyTelemetry",
    "invoke_provider_with_telemetry",
    "invoke_with_model_telemetry",
]
