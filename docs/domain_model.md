# Phase 1 Domain Model

<details open>
<summary><strong>1. Purpose</strong></summary>

This document defines the initial recruitment-domain model for Phase 1.

It is a planning baseline for the Supabase schema, ingestion endpoints, retrieval logic, and future LangGraph workflows.

The model should support a narrow but useful first version of the GraphRAG recruitment intelligence system without trying to represent every future workflow.

Phase 1 should focus on:

- Canonical recruitment entities.
- Source-system records.
- Relationships between entities.
- Provenance and auditability.
- Document chunks and embeddings.
- Match results and feedback.
- Proposed workflow actions.

</details>

<details open>
<summary><strong>2. Modelling Principles</strong></summary>

The database should follow these principles:

- Preserve raw source records before transforming them.
- Store stable canonical entities separately from source-system payloads.
- Use relationship/link tables to model the graph.
- Track source, confidence, timestamps, and provenance wherever possible.
- Avoid overwriting human-confirmed data with generated recommendations.
- Keep LLM outputs traceable to source records, entities, documents, chunks, prompts, and model versions.
- Start narrow, but do not block obvious future extension.

</details>

<details open>
<summary><strong>3. Core Canonical Entities</strong></summary>

## Companies

Represents an organisation that may employ candidates, hire for jobs, contain contacts, or appear in source records.

Likely fields:

- `id`
- `name`
- `domain`
- `website_url`
- `linkedin_url`
- `industry`
- `size_range`
- `location`
- `description`
- `status`
- `created_at`
- `updated_at`

## People

Represents a human being before assigning a specific recruitment role.

A person may be a candidate, contact, hiring manager, or more than one of these.

Likely fields:

- `id`
- `full_name`
- `first_name`
- `last_name`
- `primary_email`
- `primary_phone`
- `linkedin_url`
- `location`
- `headline`
- `summary`
- `created_at`
- `updated_at`

## Candidates

Represents a person in a candidate context.

Likely fields:

- `id`
- `person_id`
- `current_title`
- `current_company_id`
- `candidate_status`
- `availability_status`
- `salary_expectation`
- `notice_period`
- `last_contacted_at`
- `created_at`
- `updated_at`

## Contacts

Represents a person in a client, contact, or hiring-manager context.

Likely fields:

- `id`
- `person_id`
- `company_id`
- `role_title`
- `contact_type`
- `seniority`
- `is_hiring_manager`
- `created_at`
- `updated_at`

## Jobs

Represents a job, opportunity, vacancy, search assignment, or hiring need.

Likely fields:

- `id`
- `company_id`
- `hiring_manager_contact_id`
- `title`
- `description`
- `location`
- `workplace_type`
- `employment_type`
- `salary_min`
- `salary_max`
- `currency`
- `status`
- `opened_at`
- `closed_at`
- `created_at`
- `updated_at`

## Skills

Represents a normalised skill or capability.

Likely fields:

- `id`
- `name`
- `canonical_name`
- `skill_type`
- `description`
- `created_at`
- `updated_at`

## Documents

Represents a source document or file-level artefact.

Examples:

- CV.
- Job specification.
- CRM note export.
- Interview note.
- Email export.
- Source-system text export.

Likely fields:

- `id`
- `document_type`
- `title`
- `source_uri`
- `storage_path`
- `mime_type`
- `content_hash`
- `extracted_text`
- `created_at`
- `updated_at`

## Interactions

Represents a communication, meeting, call, note, or event involving one or more entities.

Likely fields:

- `id`
- `interaction_type`
- `occurred_at`
- `subject`
- `body`
- `summary`
- `source_system`
- `created_at`
- `updated_at`

## Source Records

Represents raw records received from external systems.

Likely fields:

- `id`
- `source_system`
- `source_record_type`
- `source_record_id`
- `source_payload`
- `source_payload_hash`
- `import_run_id`
- `received_at`
- `processed_at`
- `sync_status`
- `error_message`

</details>

<details>
<summary><strong>4. Relationship Tables</strong></summary>

Phase 1 should model relationships explicitly instead of hiding them in JSON blobs.

Recommended relationship tables:

## `candidate_skills`

Links candidates to skills.

Useful fields:

- `candidate_id`
- `skill_id`
- `source_record_id`
- `confidence`
- `evidence_text`
- `created_at`

## `job_required_skills`

Links jobs to required or preferred skills.

Useful fields:

- `job_id`
- `skill_id`
- `requirement_type`
- `importance`
- `source_record_id`
- `created_at`

## `person_company_roles`

Links people to companies over time.

Useful fields:

- `person_id`
- `company_id`
- `role_title`
- `start_date`
- `end_date`
- `is_current`
- `source_record_id`
- `confidence`

## `document_links`

Links documents to canonical entities.

Useful fields:

- `document_id`
- `entity_type`
- `entity_id`
- `relationship_type`
- `source_record_id`
- `created_at`

## `interaction_participants`

Links interactions to people, companies, candidates, contacts, or jobs.

Useful fields:

- `interaction_id`
- `entity_type`
- `entity_id`
- `participant_role`
- `created_at`

## `source_record_links`

Links raw source records to canonical entities.

Useful fields:

- `source_record_id`
- `entity_type`
- `entity_id`
- `mapping_confidence`
- `mapping_status`
- `created_at`

</details>

<details>
<summary><strong>5. Documents, Chunks, and Embeddings</strong></summary>

Phase 1 should support semantic retrieval without treating vector search as the whole GraphRAG system.

## Document Chunks

Represents retrievable text chunks derived from documents or source text.

Likely fields:

- `id`
- `document_id`
- `chunk_index`
- `content`
- `token_count`
- `metadata`
- `created_at`

## Embeddings

Embeddings can either live directly on document chunks or in a separate embedding table.

For Phase 1, prefer a separate table if multiple embedding models may be tested.

Likely fields:

- `id`
- `chunk_id`
- `embedding_model`
- `embedding_dimensions`
- `embedding`
- `created_at`

Notes:

- Use `pgvector`.
- Track model and dimensions.
- Chunks must link back to documents and canonical entities through provenance.
- Do not let summaries replace source text.

</details>

<details>
<summary><strong>6. Matching, Feedback, and Actions</strong></summary>

## Match Results

Represents a generated match between a query object and candidate result objects.

Examples:

- Job-to-candidate match.
- Candidate-to-company match.
- Company-to-contact match.

Likely fields:

- `id`
- `match_type`
- `query_entity_type`
- `query_entity_id`
- `result_entity_type`
- `result_entity_id`
- `score`
- `confidence`
- `rationale`
- `evidence`
- `model_provider`
- `model_name`
- `workflow_version`
- `created_at`

## Feedback

Represents recruiter feedback on generated matches or recommendations.

Likely fields:

- `id`
- `match_result_id`
- `user_id`
- `rating`
- `feedback_text`
- `outcome`
- `created_at`

## Proposed Actions

Represents an action the system suggests but does not necessarily execute.

Examples:

- Create task.
- Draft email.
- Send Slack notification.
- Update CRM record.
- Start outreach workflow.

Likely fields:

- `id`
- `action_type`
- `target_entity_type`
- `target_entity_id`
- `payload`
- `status`
- `requires_approval`
- `approved_by`
- `approved_at`
- `rejected_by`
- `rejected_at`
- `created_at`

</details>

<details>
<summary><strong>7. Identity and Deduplication Signals</strong></summary>

Initial deduplication should consider:

- Email address.
- Phone number.
- LinkedIn URL or public identifier where legally usable.
- Company domain.
- Source-system IDs.
- Person name plus company plus role.
- CV/document fingerprints.
- Interaction history.
- Employment overlap.
- Skill overlap.

The schema should eventually support:

- Confidence scores.
- Merge decisions.
- Split decisions.
- Manual override history.
- Source-of-truth rules.

</details>

<details>
<summary><strong>8. Phase 1 First Workflow Assumption</strong></summary>

Unless changed by the business priority, the first workflow should be:

```text
job-to-candidate matching
```

This means Phase 1 schema should prioritise:

- Jobs.
- Candidates.
- People.
- Companies.
- Skills.
- Documents.
- Document chunks.
- Source records.
- Match results.
- Feedback.
- Proposed actions.

</details>

<details>
<summary><strong>9. Open Questions</strong></summary>

Before writing full migrations, resolve:

- Which source system provides the first real job records?
- Which source system provides the first real candidate records?
- Are CV documents stored in Supabase Storage, externally, or metadata-only in Phase 1?
- Which fields are sensitive and need stricter access controls?
- Is job-to-candidate matching confirmed as the first workflow?
- What is the first canonical skill vocabulary strategy?
- Which source wins when two systems disagree?
- What data is safe to use from LinkedIn-derived sources?
- What actions require approval in the first workflow?

</details>
