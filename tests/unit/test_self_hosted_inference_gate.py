"""Tests for the deterministic self-hosted inference benchmark gate."""

from __future__ import annotations

import json
from pathlib import Path

from backend.llm.self_hosted_gate import evaluate_self_hosted_inference_gate


def _qualified_evidence() -> dict:
    return {
        "representative_workload_data": True,
        "representative_workload_samples": 500,
        "active_workflow_count": 9,
        "active_workflows_covered": 9,
        "evaluation_suite_approved": True,
        "candidate_model_license_approved": True,
        "security_and_data_boundary_approved": True,
        "operations_owner_assigned": True,
        "benchmark_hardware_available": True,
        "hardware_capacity_headroom_ratio": 0.25,
        "monthly_provider_cost_usd": 2_000,
        "monthly_self_hosted_tco_usd": 1_000,
        "monthly_billable_tokens": 60_000_000,
        "peak_sustained_requests_per_second_15m": 1.5,
        "p95_latency_ms": 10_000,
        "p95_latency_budget_ms": 5_000,
        "provider_latency_share": 0.8,
        "third_party_processing_prohibited": False,
        "provider_continuity_requirement_unmet": False,
        "required_provider_outage_rto_minutes": 60,
    }


def test_gate_authorizes_benchmark_when_prerequisites_and_benefit_are_met() -> None:
    result = evaluate_self_hosted_inference_gate(_qualified_evidence())

    assert result["benchmark_authorized"] is True
    assert result["decision"] == "benchmark_authorized"
    assert result["failed_prerequisites"] == []
    assert set(result["met_benefit_triggers"]) == {
        "sustained_volume",
        "economic_break_even",
        "provider_dominated_latency_gap",
    }
    assert result["derived_metrics"] == {
        "self_hosted_to_provider_cost_ratio": 0.5,
        "p95_latency_to_budget_ratio": 2.0,
    }


def test_gate_fails_closed_when_benefit_exists_but_readiness_is_missing() -> None:
    evidence = _qualified_evidence()
    evidence["third_party_processing_prohibited"] = True
    evidence["benchmark_hardware_available"] = False

    result = evaluate_self_hosted_inference_gate(evidence)

    assert result["benchmark_authorized"] is False
    assert result["decision"] == "do_not_benchmark"
    assert "benchmark_hardware_ready" in result["failed_prerequisites"]
    assert "privacy_or_residency_requirement" in result["met_benefit_triggers"]


def test_gate_fails_closed_for_missing_or_invalid_measurements() -> None:
    evidence = _qualified_evidence()
    evidence.update(
        {
            "monthly_provider_cost_usd": None,
            "monthly_self_hosted_tco_usd": -1,
            "p95_latency_ms": float("nan"),
            "provider_latency_share": 1.5,
        }
    )

    result = evaluate_self_hosted_inference_gate(evidence)

    assert result["benchmark_authorized"] is False
    assert result["derived_metrics"] == {
        "self_hosted_to_provider_cost_ratio": None,
        "p95_latency_to_budget_ratio": None,
    }
    assert result["benefit_triggers"]["economic_break_even"] is False
    assert result["benefit_triggers"]["provider_dominated_latency_gap"] is False


def test_committed_current_assessment_matches_the_executable_gate() -> None:
    artifact_path = Path(
        "docs/evaluation/self_hosted_inference_gate_2026-08-05.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    result = evaluate_self_hosted_inference_gate(artifact["evidence"])

    assert result == artifact["assessment"]
    assert result["decision"] == "do_not_benchmark"
