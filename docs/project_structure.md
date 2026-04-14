# Proposed Project Structure

<details open>
<summary><strong>1. Purpose</strong></summary>

This document defines the proposed repository layout for the Phase 1 implementation of the GraphRAG recruitment intelligence system.

It is a **planning document only**. The folders and files below should not be treated as already implemented unless they exist in the repository.

The preferred implementation direction is:

- Keep the existing **Next.js starter app** as the Vercel-hosted web shell and future frontend.
- Add a **Python backend** for the intelligence layer.
- Use **FastAPI** as the Python HTTP application layer.
- Use **LangChain v1** for model, retriever, tool, and structured output abstractions.
- Use **LangGraph** for controlled multi-step workflows.
- Keep the backend modular so retrieval, ingestion, database access, evaluation, and workflow orchestration do not become tangled.

</details>

<details open>
<summary><strong>2. Design Position</strong></summary>

The repository should remain a single Vercel project with two clear application surfaces:

- `app/` for the Next.js frontend and future admin/review UI.
- `api/` for Vercel Python function entrypoints.

The actual Python business logic should live outside `api/`, under `backend/`. This keeps Vercel-specific adapter code thin and makes the backend easier to test locally.

The high-level boundary is:

```text
app/        -> Next.js frontend routes and UI
api/        -> thin Vercel Python function entrypoints
backend/    -> Python backend application, domain logic, GraphRAG, LangChain, LangGraph
supabase/   -> database migrations, seeds, and schema notes
tests/      -> Python unit, integration, and evaluation tests
fixtures/   -> source-record samples and evaluation datasets
scripts/    -> local operational scripts
docs/       -> architecture, planning, contracts, and implementation notes
setup/      -> local, Vercel, and Supabase setup instructions
```

</details>

<details open>
<summary><strong>3. Proposed Tree</strong></summary>

```text
james-joseph-associates/
|-- AGENTS.md
|-- CLAUDE.md
|-- README.md
|-- .gitignore
|-- .env.example
|-- vercel.json
|-- package.json
|-- package-lock.json
|-- next.config.ts
|-- tsconfig.json
|-- eslint.config.mjs
|-- postcss.config.mjs
|-- next-env.d.ts
|
|-- app/
|   |-- layout.tsx
|   |-- page.tsx
|   |-- globals.css
|   |-- favicon.ico
|   |
|   |-- (site)/
|   |   |-- page.tsx
|   |   `-- loading.tsx
|   |
|   |-- (admin)/
|   |   |-- layout.tsx
|   |   |-- dashboard/
|   |   |   `-- page.tsx
|   |   |-- matches/
|   |   |   `-- page.tsx
|   |   |-- entities/
|   |   |   `-- page.tsx
|   |   `-- actions/
|   |       `-- page.tsx
|   |
|   `-- api/
|       `-- README.md
|
|-- api/
|   |-- index.py
|   `-- health.py
|
|-- backend/
|   |-- __init__.py
|   |-- main.py
|   |-- settings.py
|   |-- logging.py
|   |-- errors.py
|   |
|   |-- api/
|   |   |-- __init__.py
|   |   |-- router.py
|   |   |-- dependencies.py
|   |   `-- v1/
|   |       |-- __init__.py
|   |       |-- health.py
|   |       |-- ingestion.py
|   |       |-- entities.py
|   |       |-- documents.py
|   |       |-- retrieval.py
|   |       |-- matching.py
|   |       |-- feedback.py
|   |       |-- actions.py
|   |       `-- approvals.py
|   |
|   |-- core/
|   |   |-- __init__.py
|   |   |-- auth.py
|   |   |-- permissions.py
|   |   |-- idempotency.py
|   |   |-- provenance.py
|   |   |-- audit.py
|   |   `-- clock.py
|   |
|   |-- db/
|   |   |-- __init__.py
|   |   |-- client.py
|   |   |-- repositories/
|   |   |   |-- __init__.py
|   |   |   |-- companies.py
|   |   |   |-- people.py
|   |   |   |-- candidates.py
|   |   |   |-- contacts.py
|   |   |   |-- jobs.py
|   |   |   |-- skills.py
|   |   |   |-- documents.py
|   |   |   |-- interactions.py
|   |   |   |-- source_records.py
|   |   |   |-- embeddings.py
|   |   |   |-- matches.py
|   |   |   `-- actions.py
|   |   `-- queries/
|   |       |-- __init__.py
|   |       |-- graph_traversal.py
|   |       |-- semantic_search.py
|   |       `-- hybrid_retrieval.py
|   |
|   |-- domain/
|   |   |-- __init__.py
|   |   |-- enums.py
|   |   |-- companies.py
|   |   |-- people.py
|   |   |-- candidates.py
|   |   |-- contacts.py
|   |   |-- jobs.py
|   |   |-- skills.py
|   |   |-- documents.py
|   |   |-- interactions.py
|   |   |-- source_records.py
|   |   |-- matches.py
|   |   `-- workflow_actions.py
|   |
|   |-- schemas/
|   |   |-- __init__.py
|   |   |-- common.py
|   |   |-- ingestion.py
|   |   |-- entities.py
|   |   |-- documents.py
|   |   |-- retrieval.py
|   |   |-- matching.py
|   |   |-- feedback.py
|   |   |-- actions.py
|   |   `-- approvals.py
|   |
|   |-- ingestion/
|   |   |-- __init__.py
|   |   |-- normalise.py
|   |   |-- validate.py
|   |   |-- deduplicate.py
|   |   |-- source_mapping.py
|   |   |-- import_runs.py
|   |   `-- quarantine.py
|   |
|   |-- documents/
|   |   |-- __init__.py
|   |   |-- extract.py
|   |   |-- chunk.py
|   |   |-- fingerprints.py
|   |   |-- metadata.py
|   |   `-- storage.py
|   |
|   |-- embeddings/
|   |   |-- __init__.py
|   |   |-- provider.py
|   |   |-- openai.py
|   |   |-- batch.py
|   |   `-- dimensions.py
|   |
|   |-- retrieval/
|   |   |-- __init__.py
|   |   |-- graph.py
|   |   |-- vector.py
|   |   |-- hybrid.py
|   |   |-- ranking.py
|   |   |-- evidence.py
|   |   `-- context_builder.py
|   |
|   |-- llm/
|   |   |-- __init__.py
|   |   |-- models.py
|   |   |-- prompts.py
|   |   |-- structured_output.py
|   |   |-- safety.py
|   |   `-- callbacks.py
|   |
|   |-- graphs/
|   |   |-- __init__.py
|   |   |-- state.py
|   |   |-- nodes.py
|   |   |-- edges.py
|   |   |-- candidate_job_match.py
|   |   |-- action_proposal.py
|   |   `-- human_approval.py
|   |
|   |-- services/
|   |   |-- __init__.py
|   |   |-- entity_service.py
|   |   |-- ingestion_service.py
|   |   |-- document_service.py
|   |   |-- retrieval_service.py
|   |   |-- matching_service.py
|   |   |-- feedback_service.py
|   |   |-- action_service.py
|   |   `-- approval_service.py
|   |
|   |-- integrations/
|   |   |-- __init__.py
|   |   |-- make/
|   |   |   |-- __init__.py
|   |   |   |-- payloads.py
|   |   |   |-- responses.py
|   |   |   `-- signatures.py
|   |   |-- supabase/
|   |   |   |-- __init__.py
|   |   |   `-- client.py
|   |   `-- providers/
|   |       |-- __init__.py
|   |       |-- openai.py
|   |       `-- openrouter.py
|   |
|   `-- evals/
|       |-- __init__.py
|       |-- datasets.py
|       |-- fixtures.py
|       |-- retrieval_eval.py
|       |-- matching_eval.py
|       |-- groundedness_eval.py
|       |-- structured_output_eval.py
|       `-- action_safety_eval.py
|
|-- supabase/
|   |-- README.md
|   |-- migrations/
|   |   |-- 0001_enable_extensions.sql
|   |   |-- 0002_core_entities.sql
|   |   |-- 0003_relationships.sql
|   |   |-- 0004_source_records.sql
|   |   |-- 0005_documents_chunks_embeddings.sql
|   |   |-- 0006_matches_feedback_actions.sql
|   |   `-- 0007_audit_provenance.sql
|   |-- seeds/
|   |   `-- dev_seed.sql
|   `-- types/
|       `-- README.md
|
|-- tests/
|   |-- conftest.py
|   |-- unit/
|   |   |-- test_ingestion.py
|   |   |-- test_deduplication.py
|   |   |-- test_chunking.py
|   |   |-- test_retrieval.py
|   |   |-- test_matching.py
|   |   `-- test_action_safety.py
|   |-- integration/
|   |   |-- test_api_health.py
|   |   |-- test_source_record_ingestion.py
|   |   |-- test_entity_search.py
|   |   `-- test_candidate_job_match.py
|   `-- evals/
|       |-- test_retrieval_fixtures.py
|       |-- test_matching_fixtures.py
|       `-- test_structured_outputs.py
|
|-- fixtures/
|   |-- README.md
|   |-- source_records/
|   |   |-- candidate_sample.json
|   |   |-- company_sample.json
|   |   `-- job_sample.json
|   |-- documents/
|   |   `-- README.md
|   `-- evals/
|       |-- retrieval_cases.jsonl
|       |-- matching_cases.jsonl
|       `-- action_safety_cases.jsonl
|
|-- scripts/
|   |-- README.md
|   |-- check_env.py
|   |-- run_evals.py
|   |-- import_source_records.py
|   |-- backfill_embeddings.py
|   `-- inspect_schema.py
|
|-- docs/
|   |-- north_star_architecture.md
|   |-- phase_1_todo.md
|   |-- project_structure.md
|   |-- domain_model.md
|   |-- api_contract.md
|   |-- source_systems_inventory.md
|   |-- make_workflows.md
|   |-- evaluation_plan.md
|   |-- security_and_permissions.md
|   `-- deployment_notes.md
|
|-- setup/
|   |-- setup.md
|   |-- local_development.md
|   |-- vercel.md
|   `-- supabase.md
|
|-- public/
|   `-- ...
|
|-- local_docs/
|   `-- ...
|
|-- requirements.txt
|-- pyproject.toml
|-- pytest.ini
|-- ruff.toml
`-- .github/
    `-- workflows/
        |-- ci.yml
        |-- evals.yml
        `-- deploy-checks.yml
```

</details>

<details>
<summary><strong>4. Folder Responsibilities</strong></summary>

### `app/`

The Next.js App Router frontend. For now this can remain the starter app. Later it can hold:

- Public site or placeholder route.
- Admin dashboard.
- Match review screens.
- Entity search screens.
- Approval queue screens.

Do not put the Python intelligence layer here.

### `api/`

Thin Vercel Python function entrypoints. These files should import and expose the real FastAPI app from `backend/`.

This directory should stay small. It should not contain domain logic, retrieval logic, prompt logic, database mapping, or LangGraph workflow definitions.

### `backend/`

The Python backend application. This should be the main home for:

- FastAPI app construction.
- Settings and environment handling.
- API route modules.
- Domain models.
- Pydantic request and response schemas.
- Supabase/Postgres access.
- Ingestion and entity resolution.
- Document extraction, chunking, and embeddings.
- GraphRAG retrieval and ranking.
- LangChain v1 provider abstraction.
- LangGraph workflows.
- Evaluation helpers.

### `backend/api/`

The HTTP layer. It should validate requests, call services, and return structured responses. It should not own the business logic.

### `backend/services/`

The application layer. Services coordinate repositories, retrieval modules, LangGraph workflows, and audit/provenance helpers.

### `backend/domain/`

The recruitment business model. This is where stable internal concepts should live: companies, people, candidates, contacts, jobs, skills, documents, interactions, source records, matches, and workflow actions.

### `backend/schemas/`

Pydantic models for API contracts and structured outputs. Keeping these separate from `domain/` avoids tying internal models too tightly to external payloads.

### `backend/db/`

Database access. Repositories should hide table-level persistence details from services.

### `backend/retrieval/`

GraphRAG retrieval mechanics:

- Structured graph traversal.
- Vector search.
- Hybrid retrieval.
- Ranking.
- Evidence assembly.
- Context building for LLM calls.

### `backend/llm/`

LangChain-facing model and output abstractions:

- Model provider selection.
- Prompt templates.
- Structured output parsing.
- Safety checks.
- Callback and tracing hooks.

### `backend/graphs/`

LangGraph workflow definitions:

- Workflow state.
- Nodes.
- Edges.
- Candidate-to-job matching.
- Action proposal.
- Human approval checkpoints.

LangGraph code should stay here rather than being scattered across route handlers or services.

### `backend/evals/`

Evaluation code that can be called from tests, scripts, or CI. This is separate from `tests/` because these modules are part of the product evaluation harness, not just test files.

### `supabase/`

Source-controlled database assets:

- Migrations.
- Seeds.
- Schema notes.
- Generated types if needed later.

The first real schema should be based on the recruitment GraphRAG model, not a tutorial table.

### `tests/`

Python tests, split by purpose:

- Unit tests for pure logic.
- Integration tests for API and database boundaries.
- Evaluation tests for retrieval, matching, structured output, and action safety.

### `fixtures/`

Small sample inputs and expected outputs:

- Example source records.
- Example document fixtures.
- Retrieval and matching evaluation cases.
- Action-safety evaluation cases.

Fixtures should be safe to commit and must not contain client-sensitive data.

### `scripts/`

Local operational scripts:

- Environment checks.
- Import helpers.
- Embedding backfills.
- Evaluation runners.
- Schema inspection.

Scripts should call backend modules instead of duplicating business logic.

</details>

<details>
<summary><strong>5. Implementation Order</strong></summary>

When the project moves from planning to implementation, the safest order is:

1. Add the minimal Python project scaffolding.
2. Add a health endpoint.
3. Add environment validation with redacted logging.
4. Add Supabase migrations for extensions and core tables.
5. Add repository and service patterns.
6. Add ingestion for source records.
7. Add document and chunking strategy.
8. Add embeddings and vector storage.
9. Add retrieval and evidence assembly.
10. Add LangChain structured-output calls.
11. Add LangGraph workflows for one narrow matching use case.
12. Add evaluation fixtures and CI gates.

LangGraph should come after the entity model, API contract, and retrieval contract are clear. Otherwise the workflow graph will encode assumptions too early.

</details>

<details>
<summary><strong>6. Initial Implementation Slice</strong></summary>

The first implementation slice should be intentionally small:

```text
api/index.py
backend/__init__.py
backend/main.py
backend/settings.py
backend/api/router.py
backend/api/v1/health.py
backend/schemas/common.py
backend/core/errors.py
pyproject.toml
requirements.txt
pytest.ini
ruff.toml
tests/integration/test_api_health.py
.env.example
```

This would prove:

- Python runs on Vercel.
- FastAPI can serve a health endpoint.
- Local settings load correctly.
- Secrets are not committed.
- The test runner works.
- The repo can support the proposed backend structure before more complex GraphRAG work begins.

</details>

<details>
<summary><strong>7. Open Decisions</strong></summary>

Before implementing this structure, resolve:

- Whether Python dependencies are managed primarily through `pyproject.toml`, `requirements.txt`, or both.
- Whether FastAPI is the confirmed Python HTTP framework.
- Whether the first deployed API path should be `/api`, `/api/v1`, or both.
- Whether Supabase migrations will be applied manually, through Supabase CLI, or through CI.
- Whether the first matching use case is job-to-candidate matching or another recruitment workflow.
- Whether the frontend should stay as a starter placeholder until backend Phase 1 is usable.

</details>
