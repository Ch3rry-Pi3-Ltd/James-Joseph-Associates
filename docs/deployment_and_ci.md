# Deployment and CI

<details open>
<summary><strong>1. Purpose</strong></summary>

This document explains how the project is checked locally, checked in GitHub Actions, and deployed through Vercel.

It is a practical operating note for the Phase 1 foundation.

It gives the repository a stable place to document:

- local test commands
- local lint commands
- local production build checks
- GitHub Actions CI behaviour
- Vercel deployment flow
- required deployment environment variables
- health-check paths
- Make.com protected test endpoint checks
- JobAdder OAuth callback checks
- known non-blocking local warnings

In plain language:

- this document answers the question:

    "How do we know the foundation is still working before and after deployment?"

- it does not define application features
- it does not define database schema
- it does not define LangChain or LangGraph workflows
- it does not contain secrets

</details>

<details open>
<summary><strong>2. Current Deployment Shape</strong></summary>

The project is currently deployed as a combined Vercel project.

The two main application surfaces are:

```text
app/  -> Next.js frontend shell
api/  -> Vercel Python function entrypoint
```

The Python backend implementation lives under:

```text
backend/
```

The Vercel-facing Python entrypoint is intentionally thin:

```text
api/index.py
```

That entrypoint imports the FastAPI application from:

```text
backend/main.py
```

The intended request flow is:

```text
client
    -> Vercel
    -> api/index.py
    -> backend.main.app
    -> backend.api.router
    -> backend.api.v1.<endpoint_group>
```

For the current health endpoint, that becomes:

```text
client
    -> GET /api/v1/health
    -> api/index.py
    -> backend.main.app
    -> backend.api.router
    -> backend.api.v1.health
```

</details>

<details open>
<summary><strong>2A. Required Environment Variables</strong></summary>

The repository documents required environment variable names in:

```text
.env.example
```

The real values belong in:

```text
.env.local
Vercel project environment variables
```

Do not commit real secret values.

## Make.com Token

Protected Make.com endpoints use:

```text
MAKE_API_TOKEN
```

This should contain only the raw token value.

Correct:

```text
MAKE_API_TOKEN=<raw-token>
```

Incorrect:

```text
MAKE_API_TOKEN=Bearer <raw-token>
```

Make.com sends the same token with the `Bearer` prefix in the HTTP header:

```text
Authorization: Bearer <raw-token>
```

In plain language:

- Vercel stores the raw token
- Make.com sends `Bearer <token>`
- the backend compares the incoming token with `MAKE_API_TOKEN`

## JobAdder OAuth Settings

The backend now also expects:

```text
JOBADDER_CLIENT_ID
JOBADDER_CLIENT_SECRET
JOBADDER_REDIRECT_URI
```

For the currently deployed public callback route, the redirect URI should be:

```text
https://james-joseph-associates.vercel.app/api/v1/integrations/jobadder/callback
```

Notes:

- these are backend-only values
- they must not be exposed to client-side code
- they must not be committed to the repository
- local development may need:

```powershell
vercel env pull .env.local --environment=production
```

because Vercel sensitive environment variables were scoped to `Production` and
`Preview`, not `Development`

</details>

<details open>
<summary><strong>3. Local Checks</strong></summary>

Before committing backend or workflow changes, run the Python checks locally.

## Python Tests

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

This checks:

- FastAPI health route behaviour
- application route wiring
- settings loading
- standard error schema behaviour
- custom validation error handling
- shared HTTP metadata helpers

Expected result:

```text
passed
```

The exact number of tests will increase over time.

## Python Linting

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

This checks Python style and common correctness issues.

Expected result:

```text
All checks passed!
```

## Next.js Production Build

Run:

```powershell
npm.cmd run build
```

This checks that the Next.js app still builds for production.

This matters even while backend work is the main focus because the repository is currently deployed as a combined Vercel project.

</details>

<details>
<summary><strong>4. GitHub Actions CI</strong></summary>

The CI workflow lives at:

```text
.github/workflows/ci.yaml
```

It currently runs on:

```text
pull_request
push to main
push to any other branch
workflow_dispatch (manual run)
```

The workflow has two jobs:

```text
Python Backend
Next.js Build
```

## Python Backend Job

The Python job:

- checks out the repository
- installs Python 3.12
- installs dependencies from `requirements.txt`
- runs Ruff
- runs Pytest

In plain language:

- the backend must lint cleanly
- the backend tests must pass
- otherwise the CI run should fail

## Next.js Build Job

The Next.js job:

- checks out the repository
- installs Node.js 22
- installs Node dependencies with `npm ci`
- runs the production build with `npm run build`

In plain language:

- the frontend shell must still build
- otherwise the CI run should fail

The workflow grants read-only repository access. The runtime used internally by
checkout/setup actions is separate from the Node.js 22 app-build runtime; no
`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` override is configured.

The `Security checks` workflow runs on the same branch/PR events, manual requests,
and a weekly schedule against default branch `main`. Its Node production audit
blocks high/critical findings; Python audit and Bandit findings also fail the job.
The optional passive staging scan is skipped unless its target is configured.

</details>

<details>
<summary><strong>5. Vercel Deployment Flow</strong></summary>

The release verification flow is:

```text
local change
    -> git commit
    -> push working branch
    -> verify GitHub Actions CI + Security checks
    -> fast-forward main to the verified revision
    -> verify main checks and the production deployment
```

With Git integration enabled, Vercel can build a push independently of GitHub
Actions. A successful push or Vercel build is not proof that CI passed, and no
enforced deployment-check gate or branch protection is currently claimed here.
Check each system explicitly. A CLI release may also run a committed feature
revision: bring `main` up to that verified revision so scheduled checks are not
left auditing old dependencies.

For this sole-developer repository, a pull request is optional. Use a clean
working tree, fetch remote refs, check for divergence, and prefer `git merge
--ff-only` when updating `main`. Do not force-push or discard unrelated changes.
Keep the previous production deployment available until live smoke checks pass.

The current Vercel project should continue to build the Next.js application and expose the Python API entrypoint through the configured rewrite.

The important backend route for deployment checks is:

```text
GET /api/v1/health
GET /api/v1/integrations/jobadder/callback
```

Expected response:

```json
{
  "status": "ok",
  "service": "james-joseph-associates-api",
  "version": "0.1.0"
}
```

In plain language:

- if this route returns `200`, the Python API app is reachable
- if this route returns `404`, route registration or Vercel routing may be wrong
- if the site cannot be reached, the Vercel deployment itself may have failed

For the live JobAdder callback route, the current public path is:

```text
https://james-joseph-associates.vercel.app/api/v1/integrations/jobadder/callback
```

If visited directly without a real OAuth `code`, the expected result is a
validation error saying the authorisation code is required.

That is still a valid smoke check because it proves the callback route is live
and wired correctly.

</details>

<details>
<summary><strong>6. Known Local Warning</strong></summary>

Local Pytest runs may show a warning similar to:

```text
PytestCacheWarning: could not create cache path ... .pytest_cache ...
```

This warning means Pytest could not write its local cache folder.

It does not mean the tests failed.

In plain language:

- test failures matter
- this cache warning is currently non-blocking
- the test summary should still be checked for `passed`

</details>

<details>
<summary><strong>7. Current Minimum Green Check</strong></summary>

Before treating a backend foundation change as healthy, run:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
npm.cmd run build
```

The expected local result is:

```text
Python tests pass
Ruff passes
Next.js production build passes
```

After pushing, the expected GitHub result is:

```text
Python Backend -> passing
Next.js Build  -> passing
```

After deployment, the expected production smoke check is:

```text
GET /api/v1/health -> 200
GET /api/v1/integrations/jobadder/callback -> validation_error if no code is supplied
```

For protected Make.com routing, the expected deployment check is:

```text
POST /api/v1/make/test-event -> 200
```

That protected check requires:

```text
Authorization: Bearer <token>
Idempotency-Key: <stable-test-key>
Content-Type: application/json
```

</details>
