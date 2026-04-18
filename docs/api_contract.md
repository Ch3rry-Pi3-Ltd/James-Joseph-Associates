# Phase 1 API Contract

<details open>
<summary><strong>1. Purpose</strong></summary>

This document defines the draft REST API contract for Phase 1 of the recruitment intelligence system.

It is a planning baseline for backend routes, request schemas, response schemas, Make.com integration, tests, and future frontend clients.

The API should stay narrow at first. It should expose business capabilities rather than leaking internal database structure.

Phase 1 API goals:

- Provide a stable health endpoint.
- Accept source records from Make.com or controlled imports.
- Search canonical entities.
- Request one narrow matching workflow.
- Capture recruiter feedback.
- Create proposed workflow actions.
- Capture approval decisions.
- Keep high-risk actions controlled and auditable.

</details>

<details open>
<summary><strong>2. API Principles</strong></summary>

The Phase 1 API should follow these principles:

- Use JSON request and response bodies.
- Use stable versioned paths under `/api/v1`.
- Validate all inputs with typed schemas.
- Return structured errors.
- Require idempotency for ingestion and external workflow calls.
- Store raw source payloads before transformation.
- Return evidence references for generated recommendations.
- Treat proposed actions as drafts unless explicitly approved.
- Keep Make.com as an external action runner, not the reasoning layer.

</details>

<details>
<summary><strong>3. Route Summary</strong></summary>

Initial route groups:

```text
GET  /api/v1/health
POST /api/v1/make/test-event
POST /api/v1/source-records
GET  /api/v1/entities/search
GET  /api/v1/entities/{entity_type}/{entity_id}/context
POST /api/v1/matches/job-candidates
POST /api/v1/feedback
POST /api/v1/actions
POST /api/v1/approvals
```

Implementation status:

```text
GET  /api/v1/health          -> implemented
POST /api/v1/make/test-event -> implemented for protected Make.com testing
all other routes             -> planned
```

</details>

<details>
<summary><strong>4. Common Conventions</strong></summary>

## Headers

Recommended headers:

```text
Content-Type: application/json
Authorization: Bearer <token>
Idempotency-Key: <stable-event-key>
X-Source-System: <source-system-name>
X-Make-Run-Id: <make-scenario-run-id>
```

Notes:

- `Authorization` is required for non-health routes once auth is implemented.
- Make.com protected routes use `Authorization: Bearer <MAKE_API_TOKEN>`.
- Vercel stores only the raw `MAKE_API_TOKEN` value, without the `Bearer` prefix.
- `Idempotency-Key` should be required for ingestion and action/approval routes.
- `Idempotency-Key` is already required for the protected Make.com test endpoint.
- `X-Make-Run-Id` is optional but useful when Make.com triggers a request.

## Entity Types

Initial entity type values:

```text
company
person
candidate
contact
job
skill
document
interaction
source_record
match_result
proposed_action
```

## Standard Error Shape

Planned error response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request body failed validation.",
    "details": []
  }
}
```

Common planned error codes:

```text
validation_error
unauthorized
forbidden
not_found
conflict
idempotency_conflict
unsupported_source_system
source_record_quarantined
matching_failed
approval_required
internal_error
```

</details>

<details>
<summary><strong>5. Health</strong></summary>

## `GET /api/v1/health`

Returns a shallow liveness response.

This endpoint should not connect to Supabase, model providers, Make.com, or other external systems.

Response:

```json
{
  "status": "ok",
  "service": "james-joseph-associates-api",
  "version": "0.1.0"
}
```

Status codes:

```text
200 -> API app and route registration are alive.
```

</details>

<details>
<summary><strong>5A. Make.com Test Event</strong></summary>

## `POST /api/v1/make/test-event`

Accepts a protected test event from Make.com.

This endpoint exists to prove the integration path before real source-record
ingestion begins.

It checks:

- bearer-token authentication
- idempotency key presence
- Make.com metadata headers
- JSON request parsing
- controlled JSON response formatting

It does not:

- store data
- create candidates
- create jobs
- call Supabase
- call LangChain
- call LangGraph
- run a real business workflow

Required headers:

```text
Authorization: Bearer <token>
Idempotency-Key: <stable-test-key>
Content-Type: application/json
```

Useful optional headers:

```text
X-Source-System: make
X-Make-Run-Id: <make-scenario-run-id>
X-Request-Id: <request-id>
```

Request:

```json
{
  "event_type": "manual_make_test",
  "payload": {
    "message": "Hello from Make.com"
  }
}
```

Response:

```json
{
  "status": "accepted",
  "message": "Make.com test event accepted.",
  "event_type": "manual_make_test",
  "idempotency_key": "make-test-001",
  "payload_hash": "<sha256>",
  "request_metadata": {
    "source_system": "make",
    "make_run_id": "test-run-001",
    "request_id": "manual-test-001"
  }
}
```

Status codes:

```text
200 -> test event accepted
401 -> missing, invalid, or unconfigured bearer token
422 -> missing or blank idempotency key
```

Notes:

- This is a proving endpoint only.
- Once this works from Make.com, the next endpoint should be real source-record
  ingestion.
- The Make.com keychain should send `Authorization: Bearer <token>`.
- Vercel should store the raw token as `MAKE_API_TOKEN`, without `Bearer`.

</details>

<details>
<summary><strong>6. Source Record Ingestion</strong></summary>

## `POST /api/v1/source-records`

Accepts a raw source-system record and stores it before canonical mapping.

This route is the main entrypoint for Make.com, CSV/import scripts, or controlled external ingestion.

Request:

```json
{
  "source_system": "jobadder",
  "source_record_type": "candidate",
  "source_record_id": "external-123",
  "source_payload": {
    "example": "raw source payload"
  },
  "received_at": "2026-04-16T12:00:00Z",
  "metadata": {
    "make_run_id": "optional-make-run-id"
  }
}
```

Required fields:

```text
source_system
source_record_type
source_record_id
source_payload
```

Planned response:

```json
{
  "source_record_id": "uuid",
  "sync_status": "accepted",
  "canonical_links": [],
  "quarantined": false
}
```

Status codes:

```text
202 -> record accepted for processing
400 -> invalid payload
401 -> missing or invalid auth
409 -> idempotency conflict
422 -> unsupported or malformed source record
```

Notes:

- The raw payload should be stored even if canonical mapping is deferred.
- Malformed records should be quarantined rather than silently discarded.
- Idempotency should use `source_system`, `source_record_type`, `source_record_id`, and/or `Idempotency-Key`.

</details>

<details>
<summary><strong>7. Entity Search</strong></summary>

## `GET /api/v1/entities/search`

Searches canonical entities.

Initial query parameters:

```text
q
entity_type
limit
offset
```

Example:

```text
GET /api/v1/entities/search?q=python%20developer&entity_type=candidate&limit=10
```

Planned response:

```json
{
  "results": [
    {
      "entity_type": "candidate",
      "entity_id": "uuid",
      "label": "Example Candidate",
      "summary": "Short safe summary.",
      "score": 0.82
    }
  ],
  "limit": 10,
  "offset": 0
}
```

Notes:

- Early implementation can be simple text search.
- Hybrid semantic search can be added after document chunks and embeddings exist.

</details>

<details>
<summary><strong>8. Entity Context</strong></summary>

## `GET /api/v1/entities/{entity_type}/{entity_id}/context`

Returns structured context for one canonical entity.

Example:

```text
GET /api/v1/entities/candidate/00000000-0000-0000-0000-000000000000/context
```

Planned response:

```json
{
  "entity_type": "candidate",
  "entity_id": "uuid",
  "summary": "Short safe summary.",
  "relationships": [],
  "documents": [],
  "interactions": [],
  "source_records": []
}
```

Notes:

- This route should become the foundation for frontend profile pages, MCP tools, and GraphRAG evidence assembly.
- It should return references, not uncontrolled long dumps of source text.

</details>

<details>
<summary><strong>9. Job-to-Candidate Matching</strong></summary>

## `POST /api/v1/matches/job-candidates`

Requests candidate recommendations for a job.

This is the assumed first Phase 1 matching workflow unless business priorities change.

Request:

```json
{
  "job_id": "uuid",
  "limit": 10,
  "constraints": {
    "location": "optional",
    "required_skills": [],
    "exclude_candidate_ids": []
  }
}
```

Planned response:

```json
{
  "match_request_id": "uuid",
  "job_id": "uuid",
  "results": [
    {
      "candidate_id": "uuid",
      "score": 0.87,
      "confidence": "medium",
      "rationale": "Short grounded explanation.",
      "evidence": [
        {
          "evidence_type": "document_chunk",
          "evidence_id": "uuid",
          "summary": "Relevant evidence summary."
        }
      ],
      "proposed_actions": []
    }
  ]
}
```

Status codes:

```text
200 -> match results returned
202 -> matching accepted for async processing
400 -> invalid request
404 -> job not found
422 -> insufficient data for matching
```

Notes:

- Every generated recommendation should include evidence references.
- Ranking should combine graph relationships and semantic retrieval once both exist.
- Early implementation may return deterministic placeholder results only after schema and test data exist.

</details>

<details>
<summary><strong>10. Feedback</strong></summary>

## `POST /api/v1/feedback`

Captures recruiter feedback on a match result or recommendation.

Request:

```json
{
  "target_type": "match_result",
  "target_id": "uuid",
  "rating": "useful",
  "feedback_text": "Good fit, but location is wrong.",
  "outcome": "shortlisted"
}
```

Planned response:

```json
{
  "feedback_id": "uuid",
  "status": "recorded"
}
```

Notes:

- Feedback should become evaluation data.
- Feedback should not directly mutate canonical entities without review rules.

</details>

<details>
<summary><strong>11. Proposed Actions</strong></summary>

## `POST /api/v1/actions`

Creates a proposed action for review or downstream execution.

Examples:

- Draft email.
- Create task.
- Send Slack notification.
- Update CRM record.
- Start outreach workflow.

Request:

```json
{
  "action_type": "draft_email",
  "target_entity_type": "candidate",
  "target_entity_id": "uuid",
  "payload": {
    "subject": "Example subject",
    "body": "Draft only."
  },
  "requires_approval": true
}
```

Planned response:

```json
{
  "proposed_action_id": "uuid",
  "status": "pending_approval",
  "requires_approval": true
}
```

Notes:

- Phase 1 should treat outreach and external mutations as approval-gated.
- Make.com should execute approved external actions, not decide whether they are safe.

</details>

<details>
<summary><strong>12. Approvals</strong></summary>

## `POST /api/v1/approvals`

Captures an approval or rejection decision for a proposed action.

Request:

```json
{
  "proposed_action_id": "uuid",
  "decision": "approved",
  "decision_by": "user-id-or-email",
  "decision_note": "Approved for draft creation."
}
```

Planned response:

```json
{
  "proposed_action_id": "uuid",
  "status": "approved",
  "execution_payload": {
    "action_type": "draft_email",
    "payload": {}
  }
}
```

Notes:

- Approval decisions must be auditable.
- The backend should return an execution payload for Make.com only after approval.
- Rejected actions should not be executed downstream.

</details>

<details>
<summary><strong>13. Open Questions</strong></summary>

Before implementing non-health routes, resolve:

- What auth method should Make.com use first?
- Which source system sends the first `source-records` payload?
- What idempotency key format should Make.com use?
- Is job-to-candidate matching confirmed as the first workflow?
- Which action types are allowed in Phase 1?
- Which action types require approval?
- Which route should be implemented first after health: source ingestion or entity search?
- Should matching be synchronous in Phase 1 or accepted as async work?

</details>
