from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
import pytest

from backend.core.observability import observe_workflow
from backend.llm import telemetry


class _StreamingRunnable:
    def __init__(self) -> None:
        self.config: dict[str, object] = {}

    def with_config(self, config: dict[str, object]) -> _StreamingRunnable:
        self.config = config
        return self

    def invoke(self, payload: dict[str, str]) -> dict[str, bool]:
        callback = self.config["callbacks"][0]  # type: ignore[index]
        run_id = uuid4()
        callback.on_chat_model_start({}, [[]], run_id=run_id)
        callback.on_llm_new_token("A", run_id=run_id)
        callback.on_llm_new_token("B", run_id=run_id)
        callback.on_llm_end(
            LLMResult(
                generations=[
                    [
                        ChatGeneration(
                            message=AIMessage(
                                content="AB",
                                usage_metadata={
                                    "input_tokens": 10,
                                    "output_tokens": 2,
                                    "total_tokens": 12,
                                },
                                response_metadata={
                                    "metrics": {
                                        "queue_time_ms": 12,
                                        "prompt_time": 0.25,
                                        "completion_time": 0.4,
                                    }
                                },
                            )
                        )
                    ]
                ],
                llm_output={
                    "token_usage": {"prompt_tokens_details": {"cached_tokens": 4}}
                },
            ),
            run_id=run_id,
        )
        return {"ok": payload["private"] == "do-not-log"}


def test_invoke_with_model_telemetry_measures_streaming_and_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = iter([0.0, 0.1, 0.3, 0.5, 0.9, 1.0])
    monkeypatch.setattr(telemetry, "perf_counter", lambda: next(clock))
    caplog.set_level(logging.INFO, logger="backend.llm.telemetry")
    caplog.set_level(logging.INFO, logger="backend.core.observability")

    with observe_workflow(
        workflow="candidate_shortlist",
        workflow_version="1.0",
        run_id="run-123",
    ):
        result, measurement = telemetry.invoke_with_model_telemetry(
            _StreamingRunnable(),
            {"private": "do-not-log"},
            workflow="candidate_shortlist_reranking",
            provider="openai",
            model="gpt-4.1-mini",
            run_id="run-123",
            prompt_version="candidate-shortlist-v1.0",
            model_profile_version="default-reasoning-v1",
        )

    assert result == {"ok": True}
    assert measurement["run_id"] == "run-123"
    assert measurement["end_to_end_ms"] == 1000.0
    assert measurement["provider_request_ms"] == 800.0
    assert measurement["framework_overhead_ms"] == 200.0
    assert measurement["time_to_first_token_ms"] == 200.0
    assert measurement["mean_inter_token_latency_ms"] == 200.0
    assert measurement["p95_inter_token_latency_ms"] == 200.0
    assert measurement["streamed_output_tokens_per_second"] == 3.333
    assert measurement["end_to_end_output_tokens_per_second"] == 2.0
    assert measurement["cached_input_tokens"] == 4
    assert measurement["provider_queue_ms"] == 12.0
    assert measurement["provider_prefill_ms"] == 250.0
    assert measurement["provider_decode_ms"] == 400.0
    assert measurement["estimated_cost_usd"] == 0.000006
    assert measurement["prompt_version"] == "candidate-shortlist-v1.0"
    assert measurement["model_profile_version"] == "default-reasoning-v1"
    assert measurement["streaming_timing_available"] is True
    assert measurement["provider_timing_available"] is True
    assert '"stage_kind":"model"' in caplog.text
    assert '"estimated_cost_usd":6e-06' in caplog.text
    assert '"cached_input_tokens":4' in caplog.text
    assert "do-not-log" not in caplog.text


def test_invoke_provider_with_telemetry_measures_embedding_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([3.0, 3.25])
    monkeypatch.setattr(telemetry, "perf_counter", lambda: next(clock))
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, total_tokens=7))

    result, measurement = telemetry.invoke_provider_with_telemetry(
        lambda: response,
        workflow="candidate_query_embedding",
        provider="openai",
        model="text-embedding-3-large",
        usage_extractor=lambda value: {
            "input_tokens": value.usage.prompt_tokens,
            "total_tokens": value.usage.total_tokens,
        },
    )

    assert result is response
    assert measurement["operation"] == "embedding"
    assert measurement["end_to_end_ms"] == 250.0
    assert measurement["provider_request_ms"] == 250.0
    assert measurement["input_tokens"] == 7
    assert measurement["total_tokens"] == 7
    assert measurement["streaming_timing_available"] is False


def test_invoke_with_model_telemetry_records_failures_without_swallowing_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FailingRunnable:
        def invoke(self, _: object) -> None:
            raise RuntimeError("provider failed")

    caplog.set_level(logging.INFO, logger="backend.llm.telemetry")

    with pytest.raises(RuntimeError, match="provider failed"):
        telemetry.invoke_with_model_telemetry(
            _FailingRunnable(),
            {},
            workflow="recruiter_qa_synthesis",
            provider="openai",
            model="gpt-4.1-mini",
        )

    assert '"status":"error"' in caplog.text
    assert '"error_type":"RuntimeError"' in caplog.text
