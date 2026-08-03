# Initial Security Assessment - 2026-07-23

## Scope

This was a non-destructive review of the Next.js/Clerk boundary, FastAPI routes,
file handling, response headers, repository secrets, Supabase access patterns,
and CI coverage. Production checks were limited to harmless `GET` requests for
health, sign-in, and signed-out API rejection. No fuzzing, brute force, load
testing, data mutation, or candidate-document retrieval was performed.

## Findings

### High - API allow-list enforcement was incomplete

Clerk authentication protected normal API routes, but the configured operator
email allow-list was enforced only by server-rendered pages. A signed-in Clerk
user outside the allow-list could therefore call API endpoints directly.

**Status:** Remediated in this change. Normal API routes now verify both the
Clerk session and `CLERK_ALLOWED_EMAILS`. Production fails closed if the
allow-list is absent.

### Medium - uploads had no explicit application size ceiling

Base64 uploads were decoded before an application-level file-size check. This
increased memory and document-parser denial-of-service risk.

**Status:** Remediated in this change with request-schema and decoded-byte
limits. Oversized files return a standard `413` response.

### Medium - no application rate limiting

Search, parsing, and LLM reranking can consume database, CPU, and provider
resources. Authentication reduces exposure but does not limit abuse by a
compromised or malfunctioning account.

**Status:** Remediated at the application layer on 3 August 2026. Migration
`0014` is applied and `API_RATE_LIMIT_ENABLED=true` is active in Vercel
Production and the current branch Preview environment. The shared Postgres
minute window uses a one-way principal fingerprint and privacy-safe route group,
fails closed if its control store is unavailable, returns standard `429`
responses with retry metadata, and keeps health checks exempt. A live protected
route returned limit `120` and remaining count `119`. Vercel Firewall remains
useful defence in depth.

### Medium - Supabase least privilege is not demonstrated in migrations

The application uses server-side Postgres connections, and the repository does
not contain row-level-security policies. This is not a browser-direct exposure,
but compromise of a broad runtime database credential would have a large blast
radius.

**Status:** Remediated for the production application on 3 August 2026. Applied
migration `0014` defines
no-login `jja_app_readonly` and `jja_app_writer` roles, removes schema-create
access from `PUBLIC`, and grants current/default table and sequence privileges.
Production now connects as a dedicated `jja_app_runtime` login that inherits
only `jja_app_writer`; it is not a superuser and cannot create roles, databases,
or schema objects. Before cutover, the credential passed canonical read and
rate-limit write smoke tests and was denied a probe table creation. After the
Vercel deployment, an authenticated live request returned `200`, canonical
company data, and active `120`/`119` rate-limit headers. The broader `postgres`
credential remains an administration/migration credential and is no longer used
by the Production application URLs.

### Low - browser security headers were incomplete

Production already supplied HSTS, but did not return explicit anti-framing,
MIME-sniffing, referrer-policy, or permissions-policy headers and disclosed the
Next.js powered-by header.

**Status:** Remediated. The existing headers remain and Clerk's installed Next.js
middleware now enforces its strict, nonce-based CSP contract with additional
object, base, framing, image and font boundaries.

### Low - resume filenames were used in response headers

Stored document names were interpolated into `Content-Disposition`. Framework
validation reduced practical exploitability, but response metadata should not
trust source filenames.

**Status:** Remediated in this change with CR/LF removal, a safe ASCII fallback,
RFC 5987 encoding for Unicode names, and `nosniff` on document responses.

### Informational - external integration routes need a distinct auth boundary

The `/api/v1/operator/*` and `/api/v1/make/*` routes are designed for bearer
clients rather than browser Clerk sessions. Applying both mechanisms would
prevent intended MCP/automation access.

**Status:** Clarified in this change. These routes bypass Clerk at the Next.js
edge and remain protected by their existing FastAPI bearer-token checks.

## Verification evidence

- Production health returned `200`.
- A signed-out request to a non-public candidate API route was rejected.
- The sign-in route returned `200`.
- A local tracked-file pattern scan found no obvious committed secret values.
- Targeted Python tests, Ruff, ESLint, and the Next.js production build are the
  required completion checks for this change.

## Next actions

1. Configure `SECURITY_TEST_BASE_URL` for a synthetic-data staging deployment.
2. Add Vercel Firewall rules as defence in depth for upload, search, shortlist,
   and operator endpoints.
3. Monitor enforced CSP reports/browser failures after deployment and extend only
   the narrow directive that a verified Clerk or application flow requires.
4. Complete the first authenticated manual test using the runbook and retain a
   redacted report under this directory.
