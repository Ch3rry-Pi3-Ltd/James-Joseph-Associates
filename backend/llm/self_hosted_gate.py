"""Deterministic admission gate for self-hosted inference benchmarking."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


MIN_REPRESENTATIVE_WORKLOAD_SAMPLES = 100
MIN_HARDWARE_HEADROOM_RATIO = 0.20
MIN_MONTHLY_BILLABLE_TOKENS = 50_000_000
MIN_PEAK_SUSTAINED_RPS_15M = 1.0
MIN_MONTHLY_PROVIDER_COST_USD = 1_000.0
MAX_SELF_HOSTED_TCO_RATIO = 0.70
MIN_LATENCY_BUDGET_OVERRUN_RATIO = 1.25
MIN_PROVIDER_LATENCY_SHARE = 0.70
MAX_REQUIRED_OUTAGE_RTO_MINUTES = 15


def evaluate_self_hosted_inference_gate(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a content-free, fail-closed self-hosting benchmark decision."""

    active_workflow_count = _non_negative_number(
        evidence.get("active_workflow_count")
    )
    active_workflows_covered = _non_negative_number(
        evidence.get("active_workflows_covered")
    )
    representative_samples = _non_negative_number(
        evidence.get("representative_workload_samples")
    )
    hardware_headroom = _non_negative_number(
        evidence.get("hardware_capacity_headroom_ratio")
    )
    provider_cost = _non_negative_number(
        evidence.get("monthly_provider_cost_usd")
    )
    self_hosted_tco = _non_negative_number(
        evidence.get("monthly_self_hosted_tco_usd")
    )
    monthly_tokens = _non_negative_number(
        evidence.get("monthly_billable_tokens")
    )
    peak_rps = _non_negative_number(
        evidence.get("peak_sustained_requests_per_second_15m")
    )
    p95_latency = _non_negative_number(evidence.get("p95_latency_ms"))
    latency_budget = _positive_number(evidence.get("p95_latency_budget_ms"))
    provider_latency_share = _ratio(evidence.get("provider_latency_share"))
    required_rto = _non_negative_number(
        evidence.get("required_provider_outage_rto_minutes")
    )

    prerequisites = {
        "representative_workload_ready": bool(
            evidence.get("representative_workload_data") is True
            and representative_samples is not None
            and representative_samples >= MIN_REPRESENTATIVE_WORKLOAD_SAMPLES
            and active_workflow_count is not None
            and active_workflow_count > 0
            and active_workflows_covered == active_workflow_count
        ),
        "evaluation_suite_approved": evidence.get("evaluation_suite_approved")
        is True,
        "candidate_model_license_approved": evidence.get(
            "candidate_model_license_approved"
        )
        is True,
        "security_and_data_boundary_approved": evidence.get(
            "security_and_data_boundary_approved"
        )
        is True,
        "operations_owner_assigned": evidence.get("operations_owner_assigned")
        is True,
        "benchmark_hardware_ready": bool(
            evidence.get("benchmark_hardware_available") is True
            and hardware_headroom is not None
            and hardware_headroom >= MIN_HARDWARE_HEADROOM_RATIO
        ),
        "tco_estimate_ready": bool(
            provider_cost is not None
            and provider_cost > 0
            and self_hosted_tco is not None
            and self_hosted_tco > 0
        ),
    }

    cost_ratio = (
        self_hosted_tco / provider_cost
        if provider_cost is not None
        and provider_cost > 0
        and self_hosted_tco is not None
        else None
    )
    latency_ratio = (
        p95_latency / latency_budget
        if p95_latency is not None and latency_budget is not None
        else None
    )
    benefit_triggers = {
        "privacy_or_residency_requirement": evidence.get(
            "third_party_processing_prohibited"
        )
        is True,
        "sustained_volume": bool(
            (monthly_tokens is not None and monthly_tokens >= MIN_MONTHLY_BILLABLE_TOKENS)
            or (peak_rps is not None and peak_rps >= MIN_PEAK_SUSTAINED_RPS_15M)
        ),
        "economic_break_even": bool(
            provider_cost is not None
            and provider_cost >= MIN_MONTHLY_PROVIDER_COST_USD
            and cost_ratio is not None
            and cost_ratio <= MAX_SELF_HOSTED_TCO_RATIO
        ),
        "provider_dominated_latency_gap": bool(
            latency_ratio is not None
            and latency_ratio >= MIN_LATENCY_BUDGET_OVERRUN_RATIO
            and provider_latency_share is not None
            and provider_latency_share >= MIN_PROVIDER_LATENCY_SHARE
        ),
        "provider_continuity_gap": bool(
            evidence.get("provider_continuity_requirement_unmet") is True
            and required_rto is not None
            and required_rto <= MAX_REQUIRED_OUTAGE_RTO_MINUTES
        ),
    }

    failed_prerequisites = [
        name for name, passed in prerequisites.items() if not passed
    ]
    met_benefit_triggers = [
        name for name, passed in benefit_triggers.items() if passed
    ]
    benchmark_authorized = not failed_prerequisites and bool(met_benefit_triggers)

    return {
        "gate_version": "1.0",
        "decision": (
            "benchmark_authorized"
            if benchmark_authorized
            else "do_not_benchmark"
        ),
        "benchmark_authorized": benchmark_authorized,
        "prerequisites": prerequisites,
        "benefit_triggers": benefit_triggers,
        "failed_prerequisites": failed_prerequisites,
        "met_benefit_triggers": met_benefit_triggers,
        "derived_metrics": {
            "self_hosted_to_provider_cost_ratio": (
                round(cost_ratio, 6) if cost_ratio is not None else None
            ),
            "p95_latency_to_budget_ratio": (
                round(latency_ratio, 6) if latency_ratio is not None else None
            ),
        },
        "thresholds": {
            "minimum_representative_workload_samples": (
                MIN_REPRESENTATIVE_WORKLOAD_SAMPLES
            ),
            "minimum_hardware_capacity_headroom_ratio": (
                MIN_HARDWARE_HEADROOM_RATIO
            ),
            "minimum_monthly_billable_tokens": MIN_MONTHLY_BILLABLE_TOKENS,
            "minimum_peak_sustained_requests_per_second_15m": (
                MIN_PEAK_SUSTAINED_RPS_15M
            ),
            "minimum_monthly_provider_cost_usd": MIN_MONTHLY_PROVIDER_COST_USD,
            "maximum_self_hosted_tco_ratio": MAX_SELF_HOSTED_TCO_RATIO,
            "minimum_latency_budget_overrun_ratio": (
                MIN_LATENCY_BUDGET_OVERRUN_RATIO
            ),
            "minimum_provider_latency_share": MIN_PROVIDER_LATENCY_SHARE,
            "maximum_required_provider_outage_rto_minutes": (
                MAX_REQUIRED_OUTAGE_RTO_MINUTES
            ),
        },
    }


def _non_negative_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        return None
    return numeric


def _positive_number(value: Any) -> float | None:
    numeric = _non_negative_number(value)
    return numeric if numeric is not None and numeric > 0 else None


def _ratio(value: Any) -> float | None:
    numeric = _non_negative_number(value)
    return numeric if numeric is not None and numeric <= 1 else None


__all__ = [
    "evaluate_self_hosted_inference_gate",
]

