"""Verify that Supabase's public schema is reachable only by backend roles."""

from __future__ import annotations

from dataclasses import dataclass

from backend.db.connection import postgres_connection


@dataclass(frozen=True)
class PublicAccessAudit:
    table_count: int
    rls_disabled_count: int
    anon_privilege_count: int
    authenticated_privilege_count: int
    backend_policy_count: int
    expected_backend_policy_count: int
    runtime_read_ok: bool
    runtime_write_ok: bool

    @property
    def passed(self) -> bool:
        return (
            self.table_count > 0
            and self.rls_disabled_count == 0
            and self.anon_privilege_count == 0
            and self.authenticated_privilege_count == 0
            and self.backend_policy_count == self.expected_backend_policy_count
            and self.runtime_read_ok
            and self.runtime_write_ok
        )


def run_audit() -> PublicAccessAudit:
    """Inspect metadata and smoke-test the private application login."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH public_tables AS (
                    SELECT c.oid, c.relrowsecurity
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r', 'p')
                )
                SELECT
                    count(*)::integer AS table_count,
                    count(*) FILTER (
                        WHERE NOT relrowsecurity
                    )::integer AS rls_disabled_count,
                    count(*) FILTER (
                        WHERE has_table_privilege(
                            'anon',
                            oid,
                            'SELECT, INSERT, UPDATE, DELETE'
                        )
                    )::integer AS anon_privilege_count,
                    count(*) FILTER (
                        WHERE has_table_privilege(
                            'authenticated',
                            oid,
                            'SELECT, INSERT, UPDATE, DELETE'
                        )
                    )::integer AS authenticated_privilege_count
                FROM public_tables
                """
            )
            table_summary = cursor.fetchone()

            cursor.execute(
                """
                SELECT count(*)::integer AS backend_policy_count
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND policyname IN (
                      'jja_app_readonly_select',
                      'jja_app_writer_insert',
                      'jja_app_writer_update',
                      'jja_app_writer_delete'
                  )
                """
            )
            policy_summary = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    pg_has_role(
                        'jja_app_runtime',
                        'jja_app_writer',
                        'MEMBER'
                    )
                    AND has_table_privilege(
                        'jja_app_runtime',
                        'public.candidates',
                        'SELECT'
                    ) AS runtime_read_ok,
                    pg_has_role(
                        'jja_app_runtime',
                        'jja_app_writer',
                        'MEMBER'
                    )
                    AND has_table_privilege(
                        'jja_app_runtime',
                        'public.api_rate_limit_windows',
                        'INSERT, UPDATE'
                    ) AS runtime_write_ok
                """
            )
            runtime_summary = cursor.fetchone()

    table_count = int(table_summary["table_count"])
    return PublicAccessAudit(
        table_count=table_count,
        rls_disabled_count=int(table_summary["rls_disabled_count"]),
        anon_privilege_count=int(table_summary["anon_privilege_count"]),
        authenticated_privilege_count=int(
            table_summary["authenticated_privilege_count"]
        ),
        backend_policy_count=int(policy_summary["backend_policy_count"]),
        expected_backend_policy_count=table_count * 4,
        runtime_read_ok=bool(runtime_summary["runtime_read_ok"]),
        runtime_write_ok=bool(runtime_summary["runtime_write_ok"]),
    )


def main() -> None:
    audit = run_audit()
    print(f"public_tables={audit.table_count}")
    print(f"rls_disabled_tables={audit.rls_disabled_count}")
    print(f"anon_privileged_tables={audit.anon_privilege_count}")
    print(
        "authenticated_privileged_tables="
        f"{audit.authenticated_privilege_count}"
    )
    print(
        "backend_policies="
        f"{audit.backend_policy_count}/{audit.expected_backend_policy_count}"
    )
    print(f"runtime_read_ok={str(audit.runtime_read_ok).lower()}")
    print(f"runtime_write_ok={str(audit.runtime_write_ok).lower()}")
    print(f"lockdown_passed={str(audit.passed).lower()}")
    if not audit.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
