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

**Status:** Open. Configure Vercel Firewall rate rules first, then add durable
per-user limits if the product expands beyond the small allow-list.

### Medium - Supabase least privilege is not demonstrated in migrations

The application uses server-side Postgres connections, and the repository does
not contain row-level-security policies. This is not a browser-direct exposure,
but compromise of a broad runtime database credential would have a large blast
radius.

**Status:** Open. Audit the production role, create a least-privileged runtime
role, and document backup/restore and credential rotation.

### Low - browser security headers were incomplete

Production already supplied HSTS, but did not return explicit anti-framing,
MIME-sniffing, referrer-policy, or permissions-policy headers and disclosed the
Next.js powered-by header.

**Status:** Remediated in this change. A carefully tested Content Security
Policy remains a follow-up because Clerk and embedded provider flows need to be
included correctly.

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
2. Add Vercel rate rules for upload, search, shortlist, and operator endpoints.
3. Audit and reduce the production Postgres role's privileges.
4. Add a report-only Content Security Policy, observe violations, then enforce.
5. Complete the first authenticated manual test using the runbook and retain a
   redacted report under this directory.
