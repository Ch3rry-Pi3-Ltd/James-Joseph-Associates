# Supabase Public-Schema Lockdown - 2026-08-05

## Outcome

The live Supabase `public` schema is no longer accessible through the `anon` or
`authenticated` API roles. The application remains operational through its
dedicated server-side `jja_app_runtime` login.

## Finding

Supabase grants broad data privileges to its API roles by default, while tables
created through raw SQL do not automatically receive RLS. The live audit found:

- `31` public application tables;
- RLS disabled on all `31`;
- effective `SELECT`, `INSERT`, `UPDATE`, and `DELETE` privileges for `anon` on
  all `31`;
- the same effective privileges for `authenticated` on all `31`; and
- sensitive OAuth connection columns within the exposed schema.

The application does not need direct browser-to-Supabase data access. Clerk
authenticates users and the FastAPI backend performs all database operations, so
there was no legitimate reason to retain these API-role grants.

Supabase's guidance requires RLS on tables in exposed schemas and documents the
default API privileges that caused this gap:

- <https://supabase.com/docs/guides/database/postgres/row-level-security>
- <https://supabase.com/docs/guides/api/securing-your-api>

## Remediation Applied

Migration `0015_lock_down_public_api.sql` was applied to Production in one
transaction. It:

1. revoked current table, sequence, and function privileges from `anon` and
   `authenticated`;
2. revoked their default privileges for future objects created by the normal
   Supabase `postgres` migration owner;
3. removed default `PUBLIC` execution rights from public-schema functions;
4. enabled RLS on every current public table; and
5. added select, insert, update, and delete policies only for the no-login
   backend roles introduced by migration `0014`.

No credentials, OAuth tokens, API keys, or passwords were rotated, revoked, or
deleted. This was an explicit owner decision. The remediation changes what the
existing Supabase API roles are permitted to access rather than changing any
credential values.

## Live Verification

The tracked audit script reported:

```text
public_tables=31
rls_disabled_tables=0
anon_privileged_tables=0
authenticated_privileged_tables=0
backend_policies=124/124
runtime_read_ok=true
runtime_write_ok=true
lockdown_passed=true
```

Two end-to-end checks then confirmed the real boundaries:

- an anonymous Supabase REST query against `candidates` returned `401`;
- a bounded `list_company_directory` request through the deployed, authenticated
  MCP backend returned `200`.

The production backend check exercises both its canonical database read and its
database-backed rate-limit/audit controls. No recruitment data or credential
values were printed or stored in the verification record.

## Residual Limitations

- PostgreSQL table state cannot prove whether an anonymous read occurred before
  the lockdown. Historical API-gateway logs should be reviewed in Supabase if
  the retained log window covers the exposure period.
- The existing external credentials remain valid because rotation was explicitly
  excluded. They are no longer readable through the closed anonymous database
  path, but they should still be handled as secrets.
- Every future public table must enable RLS and define its backend policies in
  its creating migration. Run `scripts/audit_supabase_public_access.py` after
  production database migrations to detect regression.
