import pytest

from scripts.smoke_mcp_endpoint import enforce_duration_budget


def test_duration_budget_accepts_values_at_or_below_limit() -> None:
    enforce_duration_budget(
        operation="Candidate search",
        duration_ms=20_000,
        maximum_ms=20_000,
    )
    enforce_duration_budget(
        operation="Candidate search",
        duration_ms=999_999,
        maximum_ms=None,
    )


def test_duration_budget_rejects_regression_without_sensitive_content() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        enforce_duration_budget(
            operation="Exhaustive CV search",
            duration_ms=10_001,
            maximum_ms=10_000,
        )

    assert str(exc_info.value) == (
        "Exhaustive CV search exceeded its 10000 ms regression budget."
    )
