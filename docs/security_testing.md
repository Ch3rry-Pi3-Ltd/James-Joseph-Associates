# Security Testing and Penetration-Test Runbook

## Purpose

This runbook defines how the recruitment intelligence application is tested
without exposing candidate data or disrupting the production service. Automated
scans provide frequent coverage, but they do not replace periodic authenticated
manual penetration testing.

## Testing cadence

| Frequency | Test | Target | Expected outcome |
| --- | --- | --- | --- |
| Every pull request and main push | Python and Node dependency audit, Bandit static analysis | Repository | Blocks high-severity dependency and high-confidence source findings |
| Weekly | Dependabot review and passive OWASP ZAP baseline | Repository and staging | Opens dependency updates and stores a web-scan report |
| Monthly | Authenticated application smoke test | Staging | Confirms Clerk access, email allow-listing, API rejection, upload limits, and CV authorization |
| Quarterly and before a major release | Manual OWASP Web/API penetration test | Staging clone with synthetic data | Tests authorization, business logic, injection, document handling, LLM boundaries, and abuse cases |
| After a material security fix | Focused retest | Staging | Demonstrates the original issue is closed without regression |

## One-time GitHub setup

1. Create a Vercel preview or staging deployment that uses a separate Supabase
   project populated only with synthetic test records.
2. In GitHub, open `Settings > Secrets and variables > Actions > Variables`.
3. Add `SECURITY_TEST_BASE_URL` with the staging origin, for example
   `https://example-security-staging.vercel.app`.
4. Open the `Security checks` workflow and run it manually once.
5. Download the `zap-security-report` artifact and triage the initial baseline.

The ZAP job is deliberately non-blocking at first. Once expected warnings are
documented, it should be changed to fail on new medium/high findings.

## Authenticated monthly checks

Use a dedicated Clerk test user that contains no real recruiter or candidate
data. Verify all of the following:

- signed-out access to every non-health API route is rejected;
- a signed-in email outside `CLERK_ALLOWED_EMAILS` receives `403`;
- an allowed user can reach only intended recruiter functions;
- bearer-protected `/api/v1/operator/*` and `/api/v1/make/*` routes reject a
  missing, malformed, or incorrect token;
- candidate IDs cannot be changed to retrieve data outside the caller's scope;
- CV preview/download responses cannot inject headers or execute active content;
- oversized, malformed, encrypted, nested, and unsupported documents fail
  cleanly;
- job descriptions, CVs, and source notes containing prompt-injection text do
  not override system instructions or expose unrelated records;
- repeated expensive searches and shortlist calls are rate-limited or blocked
  by deployment controls;
- errors do not return secrets, connection strings, SQL, provider tokens, or
  stack traces.

## Quarterly manual test scope

The manual assessment should use the OWASP Web Security Testing Guide and OWASP
API Security Top 10 as its baseline. It must include:

- Clerk session handling, allow-list enforcement, logout, and stale sessions;
- object-level and function-level authorization across candidates, companies,
  contacts, jobs, opportunities, interactions, and documents;
- SQL injection, reflected/stored XSS, header injection, SSRF, path traversal,
  ZIP/document parser abuse, and malicious file metadata;
- OAuth callback/state handling for Dropbox, Outlook, and any live CRM;
- operator/MCP bearer-token isolation and token rotation;
- Supabase role privileges, backups, network exposure, and recovery testing;
- LLM prompt injection, cross-record data leakage, excessive context retrieval,
  unsafe tool calls, and output grounding;
- resource exhaustion around uploads, PDF parsing, semantic retrieval, and LLM
  reranking.

## Production safety rules

- Do not run active scanners, brute force, payload fuzzing, or load tests against
  production without a written test window and explicit authorization.
- Never place real CVs, API keys, OAuth tokens, or production database dumps in
  scanner artifacts.
- Start with staging and synthetic data. Production checks should normally be
  limited to passive headers, TLS, and authentication rejection.
- Stop immediately if error rates, latency, provider costs, or database load rise.

## Evidence and remediation

Store each assessment under `docs/security/` with the date, scope, environment,
tools, findings, evidence, owner, remediation commit, and retest result. Findings
should be ranked as critical, high, medium, low, or informational and must avoid
including secrets or unnecessary personal data.
