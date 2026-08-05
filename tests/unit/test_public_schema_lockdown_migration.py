"""Regression contract for the server-only Supabase public schema."""

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "0015_lock_down_public_api.sql"
)


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8").lower()


def test_public_api_roles_lose_current_and_future_object_privileges() -> None:
    sql = _migration_sql()

    assert "array['anon', 'authenticated']" in sql
    assert "revoke all privileges on all tables in schema public" in sql
    assert "revoke all privileges on all sequences in schema public" in sql
    assert "revoke all privileges on all functions in schema public" in sql
    assert "alter default privileges for role postgres" in sql
    assert "revoke execute on functions from public" in sql


def test_every_public_table_gets_rls_and_backend_only_policies() -> None:
    sql = _migration_sql()

    assert "c.relkind in ('r', 'p')" in sql
    assert "alter table %s enable row level security" in sql
    assert "for select to jja_app_readonly using (true)" in sql
    assert "for insert to jja_app_writer with check (true)" in sql
    assert (
        "for update to jja_app_writer using (true) with check (true)" in sql
    )
    assert "for delete to jja_app_writer using (true)" in sql
    assert "bypassrls" not in sql
    assert "to anon" not in sql
    assert "to authenticated" not in sql
