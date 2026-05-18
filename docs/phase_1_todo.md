# Phase 1 To-Do List

<details open>
<summary><strong>Phase 1 Objective</strong></summary>

Phase 1 should establish the **minimum viable technical foundation** for the GraphRAG recruitment intelligence system without overbuilding the full agentic platform.

The objective is to create a project foundation that can support:

- **Supabase as the central data and memory layer**
- **Recruitment-domain relational graph modelling**
- **Vercel-hosted backend services**
- **LangChain v1 and LangGraph orchestration**
- **Make.com workflow integration**
- **Clean REST APIs**
- **CI/CD, automated testing, and LLM evaluation**
- **Controlled lead recommendation, pattern discovery, and workflow assistance**

</details>

<details open>
<summary><strong>0. Immediate Priority Queue</strong></summary>

These items have now moved to the top of the practical working order because
they were reinforced by recent live JobAdder extraction work and by the
client's latest feedback.

- [ ] Add a robust Supabase persistence verification mechanism for accepted
  JobAdder CV ingests:
  - [x] Verify the canonical person, candidate, company, document, and
    candidate-skill rows after write.
  - [x] Verify source-record provenance links after write.
  - [x] Produce an operator-friendly inspection/check script for a persisted
    candidate snapshot.
  - [ ] Decide what should count as a persistence pass/fail before bulk loads.
- [x] Show the current Supabase canonical fields/entities clearly so they can
  be reviewed against business requirements before wider ingestion.
- [x] Extend persistence design for no-CV / sparse-profile cases so valuable
  JobAdder contacts are still retained even when there is no strong resume
  document.
- [x] Confirm how JobAdder notes should move from provenance-bearing payloads
  into first-class persisted interaction/note records.
- [ ] Confirm LinkedIn URL handling as a first-class persisted identifier for
  later refresh/reconciliation work.
- [ ] Set up what is required for Dropbox source access and inspect the
  expected file structure before broader import design.
  - [x] Document the first-pass Dropbox access/setup and source-shape review
    checklist in `docs/dropbox_access_setup_checklist.md`.
  - [x] Scaffold Dropbox OAuth backend support:
    - [x] Dropbox authorize URL route.
    - [x] Dropbox callback route.
    - [x] Dropbox token persistence.
    - [x] First authenticated Dropbox reads for:
      - [x] current account
      - [x] folder preview
    - [x] Broaden Dropbox app scopes up front so later Outlook-to-Dropbox file
      staging does not require a second consent flow.
  - [ ] Confirm Dropbox app registration ownership and live app credentials.
  - [ ] Confirm first folders in scope.
    - [x] Record the current candidate first-target folders:
      - [x] `/tw394 = to CVR`
      - [x] `/### BIG BAD CV ARCHIVE inc. RFL/######## ADV&JBS-CVR-bklg/tw337 adv-cvr upload`
    - [ ] Confirm whether the first narrow file-read/download slice should use
      `tw394 = to CVR` or `tw337 adv-cvr upload`.
  - [ ] Confirm whether the first pass should be strictly read-only.
  - [ ] Inspect a 20-30 file sample and record matching/source-shape findings.
    - [x] Record the first live folder-shape findings in
      `docs/dropbox_source_shape_review.md`.
    - [x] Build the first Dropbox file download/read helper for a narrow sample.
    - [x] Verify PDF reads from Dropbox end to end.
    - [x] Verify DOCX reads from Dropbox end to end.
      - [x] Note that at least one real Dropbox DOCX is malformed and fails
        local extraction with "The resume DOCX does not contain the main
        document body."
    - [x] Decide how to handle legacy `.doc` files:
      - [ ] add native extraction support
      - [x] classify them as a staged/manual-conversion path
      - [x] current decision basis:
        - [x] no obvious local `.doc` conversion tool is installed
        - [x] first target folder `tw394 = to CVR` contains `0` `.doc` files
        - [x] `tw337 adv-cvr upload` contains `1` `.doc` file
        - [x] `tw396/WIP in GPT` contains `1` `.doc` file
        - [x] one real `.doc` download fails with the current expected error:
          `The resume file format is not supported for text extraction.`
    - [ ] Record file-type handling policy in documentation:
      - [x] PDF supported
      - [x] DOCX supported
      - [x] DOC not supported in the first automated path; stage for manual
        conversion or later tooling if volume justifies it
- [ ] Review the wider source-system landscape and recommended import order
  before bulk loading old/static CV data:
  - [ ] JobAdder.
  - [ ] Dropbox CV folders.
    - [ ] Split Dropbox ingestion policy into:
      - [ ] generic CV/document-source folders
      - [ ] advert-response / vacancy-linked folders
      - [x] Prove that a small advert-response folder can feed the existing
        PDF/DOCX extraction path:
        - [x] `tw337 adv-cvr upload` PDF proof
        - [x] `tw337 adv-cvr upload` DOCX proof
    - [ ] Preserve vacancy-code (`tw...`) metadata for advert-response folders.
    - [ ] Decide whether advert-response Dropbox CVs should be modelled as:
      - [ ] document-first candidate evidence
      - [ ] vacancy-aware applications
      - [ ] or a hybrid path
  - [ ] Outlook / Microsoft 365 CV attachments.
    - [x] Scaffold Outlook OAuth backend support:
      - [x] Outlook authorize URL route.
      - [x] Outlook callback route.
      - [x] Outlook token persistence.
      - [x] First authenticated Microsoft Graph reads for:
        - [x] current user
        - [x] mail folders
        - [x] folder messages
        - [x] message attachments
    - [ ] Confirm Microsoft app registration ownership and live app credentials.
    - [ ] Confirm whether the first mailbox read should target Tom directly or a delegated/shared mailbox path.
    - [ ] Inspect a first mailbox folder sample and record attachment/source-shape findings.
  - [ ] LinkedHelper / LinkedIn-derived refresh data.
  - [ ] Recruiterflow JSON.
  - [ ] Pipedrive hiring-manager data.
  - [ ] Spreadsheets / Microsoft To Do / other legacy exports.
  - [ ] Inspect the JobAdder jobs / job ads / job applications surface before
    finalising advert-response ingestion design:
    - [x] confirm the exact endpoints and fields we care about
      - [x] `GET /jobads`
      - [x] `GET /jobads/{adId}`
      - [x] `GET /jobads/{adId}/applications`
      - [x] `GET /jobads/{adId}/applications/active`
    - [ ] check whether vacancy codes or job-ad references can anchor
      Dropbox/Outlook advert-response CVs
    - [ ] decide whether JobAdder should be the structured system of record for
      advert-response/application context

</details>

<details open>
<summary><strong>1. Set Up the Vercel Project Foundation</strong></summary>

This should come first because the backend will be the system boundary for API contracts, environment configuration, deployments, and future Make.com integration.

- [x] Create or confirm the **GitHub repository** that will hold the implementation.
- [x] Create the **Vercel project** for the backend application.
- [x] Deploy the initial **Next.js starter app** to Vercel.
- [x] Decide whether the initial backend will be:
  - [ ] A dedicated backend-only Vercel project.
  - [x] A combined backend/frontend project with frontend routes deferred.
- [x] Define initial Vercel environments:
  - [x] Development.
  - [x] Preview/staging.
  - [x] Production.
- [x] Document the expected environment variables without adding secret values to the repository.
- [x] Confirm how Vercel deployments will be triggered from GitHub.
- [x] Confirm whether the Supabase integration will be managed through the **Vercel Marketplace** or configured manually.
- [ ] Add deployment ownership notes:
  - [ ] Who owns Vercel access.
  - [ ] Who can deploy to production.
  - [ ] Who can manage secrets.

</details>

<details>
<summary><strong>1A. Define and Set Up the Project Structure</strong></summary>

This should happen before backend implementation so Python, LangChain v1, LangGraph, Supabase migrations, tests, fixtures, and future frontend work have clear ownership boundaries.

- [x] Document the proposed project tree in `docs/project_structure.md`.
- [x] Confirm the initial foundation repository layout before creating implementation folders.
- [x] Add Python project metadata:
  - [x] `pyproject.toml`.
  - [x] `requirements.txt`, if needed for Vercel Python dependency installation.
  - [x] `pytest.ini`.
  - [x] `ruff.toml`.
- [x] Add thin Vercel Python entrypoints under `api/`.
- [x] Add the modular Python backend package under `backend/`.
- [x] Add Supabase migration structure under `supabase/`.
- [x] Add test structure under `tests/`.
- [ ] Add safe sample data and evaluation fixtures under `fixtures/`.
- [x] Add local operational scripts under `scripts/`.
- [x] Add GitHub Actions workflow structure under `.github/workflows/`.
- [x] Verify the structure locally with:
  - [x] Python health endpoint test.
  - [x] Next.js build.
  - [x] Vercel deployment.

</details>

<details>
<summary><strong>2. Establish Supabase as the Central Data and Memory Layer</strong></summary>

Supabase should be treated as the **canonical data platform**, not merely a vector database.

- [x] Create or confirm the **Supabase project**.
- [x] Decide whether Supabase is provisioned directly or via the **Vercel Supabase integration**.
- [ ] Enable required Supabase capabilities:
  - [x] Postgres.
  - [ ] pgvector.
  - [ ] Storage, if documents are stored directly in Supabase.
  - [ ] Auth, if needed in Phase 1 or deferred to a later phase.
- [x] Define environment separation:
  - [x] Development database.
  - [x] Preview/staging database.
  - [x] Production database.
- [ ] Define initial database access policy:
  - [ ] Backend service role access.
  - [ ] Read/write boundaries.
  - [ ] Future row-level security assumptions.
- [x] Document Supabase connection variables required by Vercel.
- [ ] Define initial backup and recovery expectations.

</details>

<details>
<summary><strong>3. Design the Phase 1 Canonical Data Model</strong></summary>

This step should happen before API implementation so the backend does not encode unstable data assumptions.

- [ ] Define canonical entities:
  - [ ] Companies.
  - [ ] People.
  - [ ] Candidates.
  - [ ] Hiring managers / contacts.
  - [ ] Jobs / opportunities.
  - [ ] Skills.
  - [ ] Documents.
  - [ ] Interactions.
  - [ ] Source-system records.
- [ ] Define relationship/link tables:
  - [ ] Candidate has skill.
  - [ ] Job requires skill.
  - [ ] Person works at company.
  - [ ] Person interacted with company/job/candidate.
  - [ ] Document belongs to person/company/job/source record.
  - [ ] Source record maps to canonical entity.
- [ ] Define **source-of-truth rules** for core fields.
- [ ] Define **sync metadata** fields:
  - [ ] Source system.
  - [ ] Source record ID.
  - [ ] Import run ID.
  - [ ] Last seen timestamp.
  - [ ] Record hash.
  - [ ] Sync status.
- [ ] Define **provenance metadata** for retrieved and generated outputs.
- [ ] Define initial deduplication signals:
  - [ ] Email.
  - [ ] Phone.
  - [ ] LinkedIn URL or identifier where legally usable.
  - [ ] Company domain.
  - [ ] Source-system IDs.
  - [ ] CV/document fingerprints.
- [ ] Add the near-term modelling rules highlighted by the current JobAdder
  ingestion work:
  - [x] No-CV / sparse-profile candidates must still be persistable as
    valuable contacts.
  - [ ] LinkedIn URL should be treated as a first-class reconciliation signal.
  - [x] Recruiter notes should move toward first-class interaction modelling,
    not remain only in provenance payloads.
  - [ ] Multiple CV/source documents must be retainable with a later
    "preferred/current CV" policy rather than destructive overwrite.

</details>

<details>
<summary><strong>4. Define the Document, Chunk, and Embedding Strategy</strong></summary>

This is the vector-store part of the GraphRAG foundation.

- [ ] Decide which Phase 1 documents are in scope:
  - [ ] CVs.
  - [ ] Job specifications.
  - [ ] CRM notes.
  - [ ] Interaction notes.
  - [ ] Source-system text exports.
- [ ] Define document metadata fields.
- [ ] Define document chunking strategy.
- [ ] Define embedding model/provider for Phase 1.
- [ ] Define embedding dimensions and storage format.
- [ ] Define pgvector index approach for the first dataset size.
- [ ] Define whether Phase 1 needs vector-only search or hybrid retrieval.
- [ ] Define how chunks link back to:
  - [ ] Source document.
  - [ ] Canonical entity.
  - [ ] Source record.
  - [ ] Import run.

</details>

<details>
<summary><strong>5. Define the Vercel Backend API Surface</strong></summary>

The backend should own **business logic, intelligence, deduplication, retrieval, ranking, matching, and guardrails**.

- [x] Draft the Phase 1 REST API contract.
- [ ] Define endpoint groups:
  - [x] Health/status.
  - [x] Candidate profile read route.
  - [x] JobAdder OAuth callback receipt route.
  - [x] Make.com protected test route.
  - [ ] Source-record ingestion.
  - [ ] Entity upsert/search.
  - [ ] Document ingestion/metadata.
  - [ ] Retrieval/matching.
  - [ ] Feedback capture.
  - [ ] Proposed workflow actions.
  - [ ] Approval decision capture.
- [ ] Define request/response schemas.
  - [x] Health response schema.
  - [x] Shared API error response schema.
  - [x] Make.com test event request/response schema.
  - [x] Candidate profile response schema.
  - [x] JobAdder OAuth callback response schema.
  - [ ] Source-record ingestion schemas.
- [x] Define validation and error conventions.
- [x] Define idempotency behaviour for protected Make.com POST requests.
- [ ] Define idempotency behaviour for real ingestion endpoints.
- [ ] Define authentication approach for:
  - [x] Make.com.
  - [ ] Internal admin users.
  - [ ] Future frontend.
  - [ ] Future MCP tools.
- [ ] Define audit logging expectations for API calls.

</details>

<details>
<summary><strong>6. Define LangChain v1 and LangGraph Responsibilities</strong></summary>

LangChain and LangGraph should support controlled backend workflows, not unconstrained agent autonomy.

- [ ] Define where **LangChain v1** is used:
  - [x] Model abstraction.
  - [ ] Tool abstraction.
  - [ ] Retriever abstraction.
  - [ ] Structured output parsing.
- [ ] Define where **LangGraph** is used:
  - [ ] Retrieval orchestration.
  - [ ] Candidate/job matching workflow.
  - [ ] Evidence assembly.
  - [ ] Action proposal workflow.
  - [ ] Human approval checkpoints.
- [x] Define foundation graph/workflow state.
- [ ] Define Phase 1 graph/workflow states.
- [ ] Define allowed tools.
- [ ] Define tool permissions.
- [ ] Define which actions require human approval.
- [x] Define initial model provider/purpose/profile assumptions.
- [ ] Define model provider fallback assumptions.

Current status:

- [x] LangGraph foundation state is implemented in `backend/graphs/state.py`.
- [x] LangGraph foundation workflow is implemented in `backend/graphs/foundation.py`.
- [x] LangGraph foundation tests are implemented in `tests/unit/test_graph_foundation.py`.
- [x] LangGraph foundation is documented in `docs/langgraph_foundation.md`.
- [x] LLM model profile foundation is implemented in `backend/llm/models.py`.
- [x] LLM model profile tests are implemented in `tests/unit/test_llm_models.py`.
- [x] LLM provider factory is implemented in `backend/llm/providers.py`.
- [x] LLM provider tests are implemented in `tests/unit/test_llm_providers.py`.
- [x] LLM model foundation is documented in `docs/llm_foundation.md`.
- [x] Resume extraction service is implemented in `backend/services/resume_extraction.py`.
- [x] Resume extraction tests are implemented in `tests/unit/test_resume_extraction.py`.
- [x] Live resume extraction runner is implemented in `scripts/run_resume_extraction.py`.
- [x] Narrow accepted-output persistence service is implemented in `backend/services/resume_extraction_persistence.py`.
- [x] Real LangChain provider clients are implemented.
- [x] Real LLM calls are implemented.
- [ ] Real GraphRAG workflow states are defined.
- [ ] Real candidate/job matching graph is implemented.

</details>

<details>
<summary><strong>7. Define the Initial GraphRAG Retrieval and Matching Scope</strong></summary>

Phase 1 should prove one useful GraphRAG workflow rather than trying to solve every recruitment workflow.

- [ ] Choose the first matching use case:
  - [ ] Job-to-candidate matching.
  - [ ] Candidate-to-company matching.
  - [ ] Skill-to-hiring-manager discovery.
  - [ ] Company lead discovery.
- [ ] Define the graph traversal inputs.
- [ ] Define the semantic retrieval inputs.
- [ ] Define the ranking criteria.
- [ ] Define the evidence required in results.
- [ ] Define structured output format for match results.
- [ ] Define confidence and explanation fields.
- [ ] Define recruiter feedback capture.
- [ ] Define what counts as a useful Phase 1 recommendation.

</details>

<details>
<summary><strong>8. Define Make.com Integration Points</strong></summary>

Make.com should be the **external orchestration/action layer**, not the intelligence layer.

- [x] Choose the first Make.com workflow.
- [ ] Define trigger source:
  - [ ] CRM/ATS update.
  - [ ] Spreadsheet row update.
  - [x] Manual trigger.
  - [ ] Scheduled import.
  - [ ] Slack/task trigger.
- [x] Define backend endpoint called by Make.com.
- [x] Define Make.com test payload format.
- [x] Define backend test response format.
- [ ] Define real source-system payload format.
- [ ] Define approved downstream actions:
  - [ ] Create task.
  - [ ] Draft email.
  - [ ] Send Slack notification.
  - [ ] Update CRM/ATS record.
  - [ ] Start outreach workflow.
- [ ] Define approval flow before high-impact actions.
- [x] Define retry key handling for the protected Make.com test endpoint.
- [ ] Define retry and failure handling for real ingestion workflows.
- [x] Define how Make.com run IDs are passed to the backend.
- [ ] Define how Make.com run IDs are logged back into Supabase.

Current status:

- [x] Make.com can call the deployed Vercel backend.
- [x] Make.com can send bearer-token authentication.
- [x] Make.com can send JSON to the backend.
- [x] Make.com can send a dynamic `Idempotency-Key` based on its execution ID.
- [x] The backend accepts the protected test event.
- [x] Integration tests cover the protected Make.com route.
- [x] Make.com service coverage notes are documented in `docs/make_service_coverage.md`.
- [x] Source-system discovery checklist is documented in `docs/source_system_discovery_checklist.md`.
- [ ] Real client source-system access is available.
- [ ] Real source-system sample payloads have been collected.
- [ ] Real source-record ingestion is designed.
- [x] Narrow accepted-output JobAdder persistence path is implemented for:
  - [x] Source records.
  - [x] Person upsert.
  - [x] Candidate upsert.
  - [x] Current company upsert.
  - [x] Resume document persistence.
  - [x] Candidate-skill refresh.
- [x] JobAdder developer application is registered.
- [x] Local JobAdder callback URI is implemented.
- [x] Live Vercel JobAdder callback URI is implemented.
- [x] JobAdder OAuth environment variables are wired into backend settings.
- [x] Server-side JobAdder token exchange is implemented.
- [x] JobAdder token storage is implemented.

</details>

<details>
<summary><strong>8A. Discover Client Source Systems</strong></summary>

This step blocks real ingestion work.

The backend foundation can accept Make.com requests, but we do not yet have
access to the client's operational source systems or representative sample
payloads.

- [x] Identify likely high-value source systems from the client tech stack.
- [x] Check which priority systems appear to have Make.com modules.
- [x] Document ways to connect unsupported services:
  - [x] HTTP/API.
  - [x] Webhooks.
  - [x] CSV or spreadsheet export.
  - [x] File watchers.
  - [x] Custom Make apps.
  - [x] Manual discovery exports.
- [x] Create source-system discovery checklist.
- [x] Create JobAdder discovery playbook.
- [ ] Get access to first source system.
- [x] Confirm first source system authentication method at a high level.
- [ ] Run first safe source-system test in Make.com.
- [ ] Capture redacted sample output from the first source system.
- [ ] Identify stable source IDs.
- [ ] Identify sensitive fields.
- [ ] Decide the first real source-record type.

Recommended first systems to inspect:

1. JobAdder.
2. LinkedHelper.
3. Dropbox CV folders.
4. Outlook CV attachments.
5. Pipedrive legacy records.
6. Google Sheets / Microsoft Excel legacy data.
7. SourceBreaker.
8. SourceWhale.

Current note:

- JobAdder is still the leading first source system.
- The application registration and callback plumbing are now in place.
- Dropbox OAuth scaffolding is now in place in the backend.
- The next Dropbox blocker is no longer auth design. It is:
  - final app registration/credentials
  - first live authorization by Tom
  - first narrow folder inspection against real Dropbox paths such as ADV-CVR

</details>

<details>
<summary><strong>9. Set Up CI/CD and Deployment Gates</strong></summary>

CI/CD should be included from the first implementation phase.

- [ ] Define GitHub branch strategy.
- [ ] Define pull request requirements.
- [ ] Define GitHub Actions checks:
  - [x] Linting.
  - [ ] Type checks.
  - [x] Unit tests.
  - [x] Integration tests.
  - [ ] API contract checks.
  - [ ] LLM evaluation checks.
  - [ ] Documentation checks.
- [ ] Define preview deployment behaviour in Vercel.
- [ ] Define production deployment approval rules.
- [ ] Define environment variable documentation checks.
- [ ] Define migration review requirements for Supabase schema changes.

</details>

<details>
<summary><strong>10. Define the Phase 1 Evaluation Harness</strong></summary>

LLM evaluation should be designed before model outputs become business-critical.

- [ ] Define deterministic checks:
  - [ ] Schema validation.
  - [ ] Required fields.
  - [ ] Entity ID validity.
  - [ ] Relationship integrity.
  - [ ] Idempotency.
- [ ] Define retrieval quality fixtures.
- [ ] Define matching quality fixtures.
- [ ] Define groundedness checks.
- [ ] Define hallucination checks.
- [ ] Define action-safety checks.
- [ ] Define minimum acceptable output format.
- [ ] Define CI pass/fail thresholds for initial evaluations.
- [ ] Define how recruiter feedback becomes evaluation data later.

Current note:

- Live resume extraction is working against real candidate data.
- Resume text extraction now supports both:
  - PDF resumes
  - DOCX resumes
- A deterministic non-LLM extraction scorer now exists for:
  - schema and required-field checks
  - source-hint comparisons
  - pass / review / rerun routing
- A separate deterministic source-CV richness assessment now exists so sparse
  CVs can be distinguished from weak extraction runs.
- The live extraction runner now supports:
  - first-pass extraction with `gpt-4.1-mini`
  - fallback reruns with `gpt-5.4-mini`
  - JSONL quality logging
- A batch runner now exists for calibration across multiple JobAdder candidates.
- The batch runner also keeps a local manifest fingerprint so:
  - unchanged successful candidates can be skipped instead of paying for duplicate LLM runs
  - unchanged no-resume source failures can be skipped instead of repeating terminal source-side misses
  - stable source failures are keyed from source-only state rather than prompt/scorer contract changes
- The immediate remaining gap is score calibration across a real candidate sample,
  not the basic extraction/fallback plumbing.
- Accepted `pass` extraction results can now be persisted on an opt-in basis from
  the CLI runners into the current canonical schema.
- That persistence slice is intentionally narrow and does not yet model:
  - recruiter notes as first-class interactions
  - full employment-history persistence
  - full project persistence
  - API-level ingestion endpoints
- The immediate next evaluation gap is now broader than extraction quality
  alone. We also need a robust post-write Supabase verification mechanism so
  accepted JobAdder CV ingests can be checked safely before any bulk push.

</details>

<details>
<summary><strong>11. Define Operational Guardrails</strong></summary>

The system should build toward useful automation while keeping high-risk actions controlled.

- [ ] Define which actions are read-only.
- [ ] Define which actions are draft-only.
- [ ] Define which actions require approval.
- [ ] Define which actions are out of scope for Phase 1.
- [ ] Define audit trail requirements.
- [ ] Define permission model assumptions.
- [ ] Define handling for low-confidence matches.
- [ ] Define handling for missing or stale source data.
- [ ] Define human review rules for outreach and CRM mutations.

</details>

<details>
<summary><strong>12. Phase 1 Completion Criteria</strong></summary>

Phase 1 should be considered complete only when the foundation can support a narrow but real workflow.

- [ ] Vercel project exists and deployment path is documented.
- [ ] Project structure is agreed and implemented.
- [ ] Supabase project exists and central data role is documented.
- [x] Make.com can securely call the backend.
- [x] Backend foundation includes health, settings, error handling, security, idempotency, and Make.com test routing.
- [x] Source-system access blocker is documented.
- [ ] Initial canonical data model is agreed.
- [ ] Initial source-of-truth and provenance rules are documented.
- [ ] REST API contract is drafted.
- [ ] GraphRAG retrieval/matching workflow is scoped.
- [ ] Make.com first workflow is scoped.
- [ ] CI/CD checks are defined.
- [ ] LLM evaluation harness is defined.
- [ ] Guardrails and approval rules are documented.
- [ ] Phase 2 dependencies and blockers are listed.

</details>
