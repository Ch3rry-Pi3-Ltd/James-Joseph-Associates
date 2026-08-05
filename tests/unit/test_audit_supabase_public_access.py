"""Tests for the public-schema security audit result."""

from scripts.audit_supabase_public_access import PublicAccessAudit


def _audit(**overrides: int | bool) -> PublicAccessAudit:
    values: dict[str, int | bool] = {
        "table_count": 31,
        "rls_disabled_count": 0,
        "anon_privilege_count": 0,
        "authenticated_privilege_count": 0,
        "backend_policy_count": 124,
        "expected_backend_policy_count": 124,
        "runtime_read_ok": True,
        "runtime_write_ok": True,
    }
    values.update(overrides)
    return PublicAccessAudit(**values)  # type: ignore[arg-type]


def test_audit_passes_only_for_complete_backend_only_lockdown() -> None:
    assert _audit().passed is True


def test_audit_fails_when_public_access_or_runtime_breakage_is_found() -> None:
    assert _audit(rls_disabled_count=1).passed is False
    assert _audit(anon_privilege_count=1).passed is False
    assert _audit(authenticated_privilege_count=1).passed is False
    assert _audit(backend_policy_count=123).passed is False
    assert _audit(runtime_read_ok=False).passed is False
    assert _audit(runtime_write_ok=False).passed is False
