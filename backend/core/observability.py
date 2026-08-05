"""Privacy-safe workflow and stage observability."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from math import isfinite
import re
from time import perf_counter
from typing import Any, Literal

from backend.core.performance import current_request_id


LOGGER = logging.getLogger("backend.core.observability")
StageKind = Literal["validation", "retrieval", "database", "model", "response"]

_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
_ALLOWED_NUMERIC_METRICS = {
    "attempt_count",
    "cache_hit_count",
    "cached_input_tokens",
    "candidate_count",
    "estimated_cost_usd",
    "input_items",
    "input_tokens",
    "output_items",
    "output_tokens",
    "records_read",
    "records_written",
    "retrieval_limit",
    "shortlist_limit",
    "total_tokens",
    "validation_rule_count",
}
_ALLOWED_BOOLEAN_METRICS = {
    "cache_hit",
    "fallback_used",
}
_ALLOWED_STRING_METRICS = {
    "attempt",
    "model",
    "model_profile_version",
    "operation",
    "prompt_version",
    "provider",
    "retrieval_mode",
    "route_intent",
}


@dataclass(slots=True)
class WorkflowObservation:
    """In-memory aggregate for one correlated workflow run."""

    workflow: str
    workflow_version: str
    run_id: str
    request_id: str | None
    parent_run_id: str | None
    started_at: float
    stage_events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event: dict[str, Any]) -> None:
        self.stage_events.append(event)


@dataclass(slots=True)
class StageObservation:
    """Mutable, strictly bounded metrics for one timed stage."""

    workflow: WorkflowObservation | None
    name: str
    kind: StageKind
    started_at: float
    metrics: dict[str, int | float | bool | str] = field(default_factory=dict)

    def set_metrics(self, **metrics: int | float | bool | str | None) -> None:
        """Attach only allow-listed, content-free scalar metrics."""

        self.metrics.update(_validated_metrics(metrics))


_current_workflow: ContextVar[WorkflowObservation | None] = ContextVar(
    "current_workflow_observation",
    default=None,
)


def current_workflow_observation() -> WorkflowObservation | None:
    """Return the active workflow observation, if any."""

    return _current_workflow.get()


@contextmanager
def observe_workflow(
    *,
    workflow: str,
    workflow_version: str,
    run_id: str,
) -> Iterator[WorkflowObservation]:
    """Bind one workflow run and emit a final content-free aggregate."""

    safe_workflow = _validated_name(workflow, field_name="workflow")
    safe_version = _validated_name(workflow_version, field_name="workflow_version")
    safe_run_id = _validated_name(run_id, field_name="run_id")
    parent = current_workflow_observation()
    observation = WorkflowObservation(
        workflow=safe_workflow,
        workflow_version=safe_version,
        run_id=safe_run_id,
        request_id=current_request_id(),
        parent_run_id=parent.run_id if parent is not None else None,
        started_at=perf_counter(),
    )
    token: Token[WorkflowObservation | None] = _current_workflow.set(observation)
    status = "success"
    error_type: str | None = None
    try:
        yield observation
    except BaseException as exc:
        status = "error"
        error_type = exc.__class__.__name__
        raise
    finally:
        duration_ms = _milliseconds(perf_counter() - observation.started_at)
        _emit_workflow_summary(
            observation,
            status=status,
            error_type=error_type,
            duration_ms=duration_ms,
        )
        _current_workflow.reset(token)


@contextmanager
def observe_stage(
    name: str,
    kind: StageKind,
    *,
    metrics: Mapping[str, int | float | bool | str | None] | None = None,
) -> Iterator[StageObservation]:
    """Measure a stage when a workflow context is active; otherwise no-op."""

    safe_name = _validated_name(name, field_name="stage")
    if kind not in ("validation", "retrieval", "database", "model", "response"):
        raise ValueError(f"Unsupported observability stage kind: {kind}")
    stage = StageObservation(
        workflow=current_workflow_observation(),
        name=safe_name,
        kind=kind,
        started_at=perf_counter(),
    )
    if metrics:
        stage.set_metrics(**dict(metrics))
    status = "success"
    error_type: str | None = None
    try:
        yield stage
    except BaseException as exc:
        status = "error"
        error_type = exc.__class__.__name__
        raise
    finally:
        if stage.workflow is not None:
            record_completed_stage(
                name=stage.name,
                kind=stage.kind,
                duration_ms=_milliseconds(perf_counter() - stage.started_at),
                status=status,
                error_type=error_type,
                metrics=stage.metrics,
            )


def record_completed_stage(
    *,
    name: str,
    kind: StageKind,
    duration_ms: float,
    status: str = "success",
    error_type: str | None = None,
    metrics: Mapping[str, int | float | bool | str | None] | None = None,
) -> None:
    """Record a pre-measured stage against the active workflow."""

    observation = current_workflow_observation()
    if observation is None:
        return
    safe_name = _validated_name(name, field_name="stage")
    safe_metrics = _validated_metrics(metrics or {})
    event: dict[str, Any] = {
        "event": "workflow_stage",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "request_id": observation.request_id,
        "run_id": observation.run_id,
        "parent_run_id": observation.parent_run_id,
        "workflow": observation.workflow,
        "workflow_version": observation.workflow_version,
        "stage": safe_name,
        "stage_kind": kind,
        "stage_index": len(observation.stage_events) + 1,
        "status": "error" if status == "error" else "success",
        "duration_ms": round(max(0.0, float(duration_ms)), 3),
        "error_type": (
            _validated_name(error_type, field_name="error_type")
            if error_type
            else None
        ),
        "metrics": safe_metrics,
    }
    observation.record(event)
    _emit("workflow_stage", event)


def _emit_workflow_summary(
    observation: WorkflowObservation,
    *,
    status: str,
    error_type: str | None,
    duration_ms: float,
) -> None:
    durations: defaultdict[str, float] = defaultdict(float)
    input_tokens = 0
    cached_input_tokens = 0
    output_tokens = 0
    estimated_cost_usd = 0.0
    failed_stage_count = 0
    for event in observation.stage_events:
        durations[event["stage_kind"]] += float(event["duration_ms"])
        metrics = event["metrics"]
        input_tokens += int(metrics.get("input_tokens") or 0)
        cached_input_tokens += int(metrics.get("cached_input_tokens") or 0)
        output_tokens += int(metrics.get("output_tokens") or 0)
        estimated_cost_usd += float(metrics.get("estimated_cost_usd") or 0.0)
        failed_stage_count += event["status"] == "error"

    summary = {
        "event": "workflow_summary",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "request_id": observation.request_id,
        "run_id": observation.run_id,
        "parent_run_id": observation.parent_run_id,
        "workflow": observation.workflow,
        "workflow_version": observation.workflow_version,
        "status": "error" if status == "error" else "success",
        "error_type": (
            _validated_name(error_type, field_name="error_type")
            if error_type
            else None
        ),
        "duration_ms": duration_ms,
        "stage_count": len(observation.stage_events),
        "failed_stage_count": failed_stage_count,
        "stage_duration_ms_by_kind": {
            key: round(value, 3) for key, value in sorted(durations.items())
        },
        "model_usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost_usd, 9),
        },
    }
    _emit("workflow_summary", summary)


def _validated_metrics(
    metrics: Mapping[str, int | float | bool | str | None],
) -> dict[str, int | float | bool | str]:
    safe: dict[str, int | float | bool | str] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        if key in _ALLOWED_BOOLEAN_METRICS:
            if not isinstance(value, bool):
                raise ValueError(f"Observability metric {key} must be boolean.")
            safe[key] = value
            continue
        if key in _ALLOWED_NUMERIC_METRICS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Observability metric {key} must be numeric.")
            numeric_value = float(value)
            if not isfinite(numeric_value) or numeric_value < 0:
                raise ValueError(
                    f"Observability metric {key} must be finite and non-negative."
                )
            safe[key] = value
            continue
        if key in _ALLOWED_STRING_METRICS:
            if not isinstance(value, str):
                raise ValueError(f"Observability metric {key} must be a string.")
            safe[key] = _validated_name(value, field_name=key)
            continue
        raise ValueError(f"Observability metric is not allow-listed: {key}")
    return safe


def _validated_name(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or _SAFE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Invalid privacy-safe observability {field_name}.")
    return value


def _milliseconds(seconds: float) -> float:
    return round(max(0.0, seconds) * 1000, 3)


def _emit(label: str, payload: dict[str, Any]) -> None:
    LOGGER.info(
        "%s %s",
        label,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )


__all__ = [
    "StageKind",
    "StageObservation",
    "WorkflowObservation",
    "current_workflow_observation",
    "observe_stage",
    "observe_workflow",
    "record_completed_stage",
]
