"""Tests for privacy-safe stage and workflow observability."""

import json
import logging

import pytest

from backend.core.observability import observe_stage, observe_workflow
from backend.core.performance import bind_request_id, reset_request_id


def _logged_payloads(caplog: pytest.LogCaptureFixture, label: str) -> list[dict]:
    prefix = f"{label} "
    return [
        json.loads(record.message.removeprefix(prefix))
        for record in caplog.records
        if record.name == "backend.core.observability"
        and record.message.startswith(prefix)
    ]


def test_workflow_correlates_safe_stage_metrics_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = iter([0.0, 0.1, 0.4, 0.5])
    monkeypatch.setattr(
        "backend.core.observability.perf_counter",
        lambda: next(clock),
    )
    request_token = bind_request_id("request-123")
    caplog.set_level(logging.INFO, logger="backend.core.observability")
    try:
        with observe_workflow(
            workflow="candidate_shortlist",
            workflow_version="1.0",
            run_id="run-123",
        ):
            with observe_stage("hybrid_retrieval", "retrieval") as stage:
                stage.set_metrics(candidate_count=5, retrieval_limit=25)
    finally:
        reset_request_id(request_token)

    stages = _logged_payloads(caplog, "workflow_stage")
    summaries = _logged_payloads(caplog, "workflow_summary")
    assert stages == [
        {
            "duration_ms": 300.0,
            "error_type": None,
            "event": "workflow_stage",
            "measured_at": stages[0]["measured_at"],
            "metrics": {"candidate_count": 5, "retrieval_limit": 25},
            "parent_run_id": None,
            "request_id": "request-123",
            "run_id": "run-123",
            "stage": "hybrid_retrieval",
            "stage_index": 1,
            "stage_kind": "retrieval",
            "status": "success",
            "workflow": "candidate_shortlist",
            "workflow_version": "1.0",
        }
    ]
    assert summaries[0]["run_id"] == "run-123"
    assert summaries[0]["duration_ms"] == 500.0
    assert summaries[0]["stage_count"] == 1
    assert summaries[0]["stage_duration_ms_by_kind"] == {"retrieval": 300.0}


def test_observability_rejects_content_bearing_metrics() -> None:
    with observe_workflow(
        workflow="candidate_shortlist",
        workflow_version="1.0",
        run_id="run-123",
    ):
        with pytest.raises(ValueError, match="not allow-listed"):
            with observe_stage(
                "hybrid_retrieval",
                "retrieval",
                metrics={"query": "private candidate search"},
            ):
                pass


def test_nested_workflows_record_parent_run_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="backend.core.observability")
    with observe_workflow(
        workflow="recruiter_qa",
        workflow_version="1.0",
        run_id="parent-run",
    ):
        with observe_workflow(
            workflow="candidate_shortlist",
            workflow_version="1.0",
            run_id="child-run",
        ):
            with observe_stage("response_assembly", "response"):
                pass

    stages = _logged_payloads(caplog, "workflow_stage")
    assert stages[0]["run_id"] == "child-run"
    assert stages[0]["parent_run_id"] == "parent-run"
