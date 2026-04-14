# North Star Architecture: GraphRAG Recruitment Intelligence System

<details open>
<summary><strong>1. Project Overview</strong></summary>


This project is an **end-to-end GraphRAG-based intelligence system** for a recruitment and search business. It will consolidate fragmented operational, CRM, ATS, document, outreach, communication, and research data into a **central data platform**, model the **relationships between the main business entities**, and expose that intelligence through **backend APIs**, **workflow automation**, and eventually a **chat/query interface**.

This document is a **planning baseline only**. It does not define completed implementation work, application scaffolding, infrastructure provisioning, or package choices beyond the architectural direction needed for later delivery.

The system is intended to solve three related business problems:

- **Data is spread across too many tools**, including legacy CRMs, spreadsheets, document stores, LinkedIn-related tools, job boards, email/calendar systems, project tools, and outreach platforms.
- **Useful relationships are not currently modelled in one place**, especially relationships between companies, candidates, hiring managers, jobs, skills, documents, previous interactions, and source-system records.
- **Search and matching work is too manual**, with too much dependency on the operator knowing where to look, how to interpret fragmented data, and how to trigger follow-up actions.

The desired end-state is a **backend-owned intelligence layer** that can:

- Maintain a **central, auditable representation** of recruitment entities and their relationships.
- Use **GraphRAG retrieval, not just vector search**, to combine structured relationship traversal with semantic retrieval from unstructured documents.
- Support **candidate, company, hiring manager, job, and skill matching**.
- Provide **clean API endpoints** for Make.com, future frontend clients, MCP tools, and operational automations.
- Trigger **downstream actions** such as CRM updates, task creation, draft emails, outreach sequences, Slack notifications, and dashboard updates through **controlled workflows**.
- Evaluate **LLM and retrieval quality from the start**, so the system improves against measurable outcomes rather than anecdotal prompt testing.


</details>
<details>
<summary><strong>2. Objectives and Non-Goals</strong></summary>


<details>
<summary><strong>Objectives</strong></summary>


- Establish **Supabase** as the **central data and memory layer**.
- Model the recruitment domain as a **relational graph** using canonical tables, link tables, source records, embeddings, document chunks, sync metadata, and provenance.
- Use **Vercel-hosted backend services** as the owner of **business logic, intelligence, deduplication, entity resolution, retrieval, ranking, matching, and guardrails**.
- Use **LangChain v1 and LangGraph** inside the backend for model abstraction, tool abstraction, controlled workflows, and stateful reasoning flows.
- Use **Make.com** as the **external orchestration/action layer** for integrations with business tools.
- Expose **clean REST APIs** that can be called by Make.com, a future chat frontend, MCP tooling, and dashboard services.
- Include **CI/CD, automated testing, and LLM evaluation** from the first implementation phase.
- Build toward an operational system that can **recommend leads, surface patterns, and assist with recruitment workflows** while keeping **high-risk actions controlled**.


</details>

<details>
<summary><strong>Non-Goals for Phase 1</strong></summary>


Phase 1 should **not** attempt to build the entire agentic platform. It should not include:

- **Full migration** of every historical data source.
- **Full two-way sync** with every active system.
- **Autonomous outreach** without review.
- A **production-grade chat UI**.
- **Advanced analytics, forecasting, Monte Carlo simulations, or market optimisation.**
- **Deep custom ML training infrastructure.**
- A **full MCP ecosystem**.
- **Complete replacement of the CRM/ATS stack.**
- **Complex multi-agent autonomy.**
- A **dashboard layer** beyond minimal operational visibility.

Phase 1 should create the **smallest sensible foundation** that later phases can extend safely.


</details>

</details>
<details>
<summary><strong>3. Recommended High-Level Architecture</strong></summary>


The recommended architecture is **backend-first** and **data-model-first**.

- **Vercel backend:** Hosts API routes, ingestion endpoints, GraphRAG orchestration, LangChain/LangGraph workflows, evaluation entry points, and integration-facing REST endpoints.
- **Supabase:** Acts as the **central data platform** using Postgres, relational modelling, pgvector embeddings, storage where appropriate, row-level security, audit tables, and sync metadata.
- **Make.com:** Acts as the **workflow orchestration layer** for external systems. It should trigger ingestion events, call backend APIs, receive structured responses, and execute **approved actions** in tools such as CRM, email, Slack, task management, and outreach platforms.
- **LangChain v1:** Provides model, retriever, tool, structured output, and chain abstractions inside the backend.
- **LangGraph:** Provides durable/stateful workflow patterns for multi-step reasoning, retrieval, matching, approval, and action-planning flows.
- **Model abstraction layer:** Provides controlled access to GPT/OpenAI, OpenRouter, Nemotron-style providers, and any future model vendors without hard-coding business logic to one provider.
- **Evaluation layer:** Provides deterministic checks, retrieval tests, structured output validation, groundedness checks, ranking quality checks, and action-safety tests.
- **CI/CD layer:** Uses GitHub and GitHub Actions to run quality gates, evaluations, and deployment workflows into Vercel-managed environments.

<details>
<summary><strong>Assumptions</strong></summary>


- **Supabase will be the canonical operational data store** for the intelligence layer, even if tools such as JobAdder, SourceWhale, Asana, Outlook, Dropbox, Google Drive, and LinkedHelper remain in active use.
- The initial backend will be hosted on Vercel, with serverless or edge/serverless-compatible API routes selected based on workload requirements.
- Make.com is valuable for integration speed, but it should **not become the system of record or the reasoning layer**.
- **Historical data quality will be inconsistent**, especially across legacy CRM/ATS records, spreadsheets, CV files, LinkedIn-derived exports, and email/document stores.
- Some data sources may have legal, contractual, or technical restrictions around scraping, automated access, or reuse. Those constraints must be checked before implementation.
- **"GraphRAG" means combining graph-style relationship traversal and semantic retrieval**, not merely storing embeddings in a vector column.
- The provided spreadsheet/PDF should be treated as **directional rather than perfectly clean**. It contains useful signals about legacy systems, active systems, and priorities, but Phase 0 should verify statuses, ownership, and integration feasibility before implementation.


</details>

</details>
<details>
<summary><strong>4. Major System Components</strong></summary>


<details>
<summary><strong>Data Ingestion Layer</strong></summary>


Responsible for bringing data into the platform from **legacy exports, active system APIs, CSV files, document stores, email/calendar systems, and Make.com-triggered events**.

Key responsibilities:

- Accept **source-system records** via REST endpoints.
- Support **batch imports** for legacy data.
- Support **event-style updates** for active systems.
- Track **source, timestamp, import run, record hash, and sync status**.
- Validate required fields and **reject or quarantine malformed inputs**.
- Preserve **raw source records** before transformation where practical.


</details>

<details>
<summary><strong>Canonical Domain and Data Model Layer</strong></summary>


Responsible for converting fragmented source data into **stable canonical entities and relationships**.

Core entities likely include:

- **Companies**
- **Candidates**
- **Hiring managers and contacts**
- **Jobs and opportunities**
- **Skills**
- **Documents**
- **Interactions**
- **Source-system records**
- **Outreach events**
- **Tasks and workflow actions**

The core modelling principle should be: **preserve raw input**, **map to canonical entities**, and **connect entities through auditable relationship tables**.


</details>

<details>
<summary><strong>GraphRAG and Retrieval Layer</strong></summary>


Responsible for combining **structured graph traversal** with **semantic retrieval**.

Example retrieval patterns:

- Find **candidates with skills** related to a new job specification, then boost those with prior positive interactions or company relevance.
- Find **hiring managers connected to companies advertising for a skillset**, then inspect prior communication history and source-system activity.
- Find **companies similar to a successful placement history** based on sector, skills, hiring patterns, geography, and relationship history.
- Retrieve **CV chunks, interaction notes, job descriptions, and LinkedIn-derived snippets**, then ground LLM reasoning in those retrieved facts.


</details>

<details>
<summary><strong>Reasoning and Agent Orchestration Layer</strong></summary>


Responsible for **controlled LLM-assisted workflows**. This layer should live in the **backend**, not in Make.com.

Key responsibilities:

- **Query planning.**
- **Retrieval orchestration.**
- **Structured output generation.**
- **Ranking and explanation.**
- **Tool selection under guardrails.**
- **Human approval routing** for high-risk actions.
- **State tracking** for multi-step workflows.


</details>

<details>
<summary><strong>API Layer</strong></summary>


Responsible for exposing a **stable contract** to Make.com, future frontend clients, MCP tools, dashboards, and internal scripts.

Initial API surface should be **narrow** and intentionally designed around **business capabilities**:

- **Ingest or update source records.**
- **Search canonical entities.**
- **Request candidate/job/company matches.**
- **Retrieve entity context.**
- **Submit feedback on match quality.**
- **Create proposed actions.**
- **Confirm or reject proposed actions.**
- **Emit workflow results for Make.com.**


</details>

<details>
<summary><strong>Workflow Automation Layer</strong></summary>


Make.com should connect **external tools** to the backend. It should handle **integration glue, scheduling, simple transformations, retries, and execution of approved actions**.

It should not:

- Own **canonical state**.
- Implement **entity resolution**.
- Own **matching logic**.
- Own **LLM prompt logic**.
- Decide autonomously whether **risky actions** should be executed.


</details>

<details>
<summary><strong>Future Frontend and Chat Layer</strong></summary>


A frontend can be added later, likely hosted on Vercel. It should call the **same backend APIs as Make.com** rather than reimplementing retrieval or workflow logic.

Likely future frontend capabilities:

- **Chat/query interface.**
- **Entity search.**
- **Match review.**
- **Workflow approval queue.**
- **Data quality review.**
- **Candidate/company/job profile pages.**
- **Evaluation feedback collection.**


</details>

<details>
<summary><strong>Analytics and Dashboard Layer</strong></summary>


Analytics should be treated as a **later phase**. Power BI or a more suitable dashboard layer can consume **curated Supabase views or exports**.

Future analytics capabilities may include:

- **Recruitment funnel metrics.**
- **Outreach activity and conversion tracking.**
- **Market/skill trend analysis.**
- **Candidate source quality.**
- **Hiring manager engagement analysis.**
- **Forecasting and resource allocation analysis.**


</details>

</details>
<details>
<summary><strong>5. Architecture Diagrams</strong></summary>


<details>
<summary><strong>High-Level Architecture</strong></summary>


```mermaid
graph LR
    subgraph Sources
        LegacyCRM[Legacy CRM and ATS]
        Spreadsheets[Excel and Google Sheets]
        Docs[Dropbox, Google Drive, and CVs]
        Comms[Outlook, Office 365, Calendly, and Ringover]
        LinkedInTools[LinkedIn, Recruiter Lite, and LinkedHelper]
        Outreach[SourceWhale, SourceBreaker, and JobAdder]
        Ops[Asana, Sunsama, Slack, and Miro]
    end

    subgraph MakeLayer
        MakeTriggers[Make triggers, schedules, and simple transforms]
        MakeActions[Make CRM, email, task, Slack, and outreach actions]
    end

    subgraph Backend
        API[REST API]
        Ingestion[Ingestion and sync handlers]
        Canonical[Canonical modelling and entity resolution]
        Retrieval[GraphRAG retrieval and ranking]
        LangGraph[LangChain v1 and LangGraph workflows]
        Guardrails[Validation, permissions, and approvals]
        EvalHooks[Evaluation hooks and telemetry]
    end

    subgraph Supabase
        Postgres[Postgres canonical tables]
        Links[Relationship link tables]
        Vectors[pgvector embeddings]
        Chunks[Document chunks]
        Raw[Raw source records]
        Audit[Audit, provenance, and sync metadata]
    end

    subgraph Models
        OpenAI[GPT and OpenAI]
        OpenRouter[OpenRouter]
        Nemotron[Nemotron-style access]
        OtherModels[Future providers]
    end

    subgraph Clients
        ChatUI[Chat and search frontend]
        MCP[MCP and tooling layer]
        BI[Power BI and analytics]
    end

    Sources --> MakeTriggers
    MakeTriggers --> API
    API --> Ingestion
    Ingestion --> Canonical
    Canonical --> Postgres
    Canonical --> Links
    Retrieval --> Postgres
    Retrieval --> Vectors
    Retrieval --> Chunks
    LangGraph --> Retrieval
    LangGraph --> Guardrails
    LangGraph --> Models
    EvalHooks --> Audit
    API --> LangGraph
    API --> Postgres
    API --> MakeActions
    MakeActions --> Sources
    ChatUI --> API
    MCP --> API
    BI --> Postgres
```


</details>

<details>
<summary><strong>Example Operational Flow: New Job to Recommended Actions</strong></summary>


```mermaid
sequenceDiagram
    participant JobSource as Job source
    participant Make as Make
    participant API as Backend API
    participant DB as Supabase
    participant Graph as GraphRAG Retrieval
    participant LLM as LLM Workflow
    participant Human as Recruiter
    participant Tools as External Tools

    JobSource->>Make: New or updated job event
    Make->>API: POST job/source record payload
    API->>API: Validate, normalise, check idempotency
    API->>DB: Store raw source record and update canonical job
    API->>DB: Link company, hiring manager, skills, documents
    API->>Graph: Request candidate/company/contact matches
    Graph->>DB: Traverse relationships and retrieve semantic chunks
    Graph->>LLM: Generate ranked, grounded match explanation
    LLM->>API: Structured match result and proposed actions
    API->>DB: Store match result, evidence, and proposed actions
    API->>Make: Return structured response
    Make->>Human: Send review task or notification
    Human->>Make: Approve, edit, or reject action
    Make->>API: Submit approval decision
    API->>DB: Record decision and audit trail
    API->>Make: Confirm action execution payload
    Make->>Tools: Create task, draft email, update CRM, notify Slack
```


</details>

<details>
<summary><strong>GraphRAG Retrieval Pattern</strong></summary>


```mermaid
graph TD
    Query[Business query]
    Intent[Intent and constraints]
    EntityLookup[Canonical entity lookup]
    GraphTraversal[Relationship traversal]
    SemanticSearch[Semantic retrieval]
    Ranker[Ranking and scoring]
    Grounding[Evidence assembly]
    LLMReasoning[LLM reasoning with structured output]
    Result[Ranked answer with evidence and allowed actions]
    Feedback[Recruiter feedback and outcome tracking]

    Query --> Intent
    Intent --> EntityLookup
    EntityLookup --> GraphTraversal
    Intent --> SemanticSearch
    GraphTraversal --> Ranker
    SemanticSearch --> Ranker
    Ranker --> Grounding
    Grounding --> LLMReasoning
    LLMReasoning --> Result
    Result --> Feedback
    Feedback --> Ranker
```


</details>

</details>
<details>
<summary><strong>6. Recommended Execution Order / Battle Plan</strong></summary>


<details>
<summary><strong>Phase 0: Discovery, Source Audit, and Design</strong></summary>


**Goal:** Establish the **data, domain, integration, and risk baseline** before implementation starts.

**Key outputs:**

- **Source systems inventory.**
- **Legacy migration map.**
- **Active integrations map.**
- **Initial domain model.**
- **Source-of-truth rules.**
- **Data quality and deduplication assessment.**
- **Security, permissions, and compliance notes.**
- **Initial API capability map.**
- **Initial evaluation plan.**

**Dependencies:**

- Client access to exports, sample records, and system owners.
- Confirmation of which systems are legacy versus active.
- Confirmation of legal and platform constraints for LinkedIn-related data, scraping, and automated access.

**Why this comes first:** **GraphRAG quality depends on the entity model and relationship quality.** Building before the source audit risks creating a technically neat system around the wrong data assumptions.


</details>

<details>
<summary><strong>Phase 1: Core Backend Foundation and Supabase Schema</strong></summary>


**Goal:** Create the **smallest reliable implementation foundation** for canonical entities, ingestion, retrieval, evaluation, and deployment.

**Key outputs:**

- **Vercel backend project structure.**
- **Supabase schema** for core canonical entities and source records.
- **Initial link tables** for people, companies, jobs, skills, documents, and interactions.
- **Initial document chunk and embedding model.**
- **Basic REST API contract.**
- **Basic ingestion endpoints** for a small number of priority sources.
- **Initial GraphRAG retrieval endpoint.**
- **Initial evaluation harness.**
- **GitHub Actions CI pipeline.**
- **Vercel deployment pipeline.**

**Dependencies:**

- Phase 0 domain model and source-of-truth decisions.
- Supabase project and environment strategy.
- Model provider decision for first implementation.
- Agreement on initial priority sources.

**Why this comes here:** **The backend and schema are the foundation** for every later workflow, chat interface, and integration. Make.com workflows should call this layer rather than compensating for its absence.


</details>

<details>
<summary><strong>Phase 2: Ingestion and Sync Endpoints</strong></summary>


**Goal:** Bring a **controlled subset of source data** into the canonical model and make **sync behaviour repeatable**.

**Key outputs:**

- **Batch import path** for selected legacy data.
- **Event-style ingestion endpoints** for selected active systems.
- **Source record mapping rules.**
- **Idempotency keys and sync metadata.**
- **Quarantine process** for invalid records.
- **Initial deduplication and entity resolution rules.**
- **Import run audit trail.**

**Dependencies:**

- Phase 1 schema and API foundation.
- Sample data from priority systems.
- Source-system identifiers and export formats.

**Why this comes here:** **Retrieval and reasoning quality require stable data ingestion.** Two-way sync is risky until canonical identity and provenance are reliable.


</details>

<details>
<summary><strong>Phase 3: GraphRAG Retrieval and Matching</strong></summary>


**Goal:** Implement the first useful intelligence capability: **grounded matching across jobs, candidates, companies, hiring managers, skills, interactions, and documents**.

**Key outputs:**

- **Retrieval patterns** combining relationship traversal and semantic search.
- **Candidate-to-job matching.**
- **Company-to-skill or market matching.**
- **Hiring-manager discovery.**
- **Evidence-backed explanations.**
- **Ranking feedback capture.**
- **Retrieval and ranking evaluation datasets.**

**Dependencies:**

- Canonical entities populated from Phase 2.
- Embedding strategy and document chunking.
- Defined quality metrics and expected outputs.

**Why this comes here:** **Matching is the central business value.** It should be built after the data foundation but before broad workflow automation.


</details>

<details>
<summary><strong>Phase 4: Make.com Integrations</strong></summary>


**Goal:** Use **Make.com** to connect the backend to active business tools and execute **controlled operational workflows**.

**Key outputs:**

- **Make.com scenarios** for selected triggers.
- **Backend API calls** from Make.com.
- **Structured response handling.**
- **Approval workflows** for high-impact actions.
- **CRM/task/email/Slack update actions.**
- **Retry and failure handling conventions.**

**Dependencies:**

- Stable backend endpoints.
- Agreed action permissions.
- Priority workflow inventory.

**Why this comes here:** **Make.com is valuable once it has a reliable backend brain to call.** Introducing it too early risks encoding business rules in scenarios that should belong in the backend.


</details>

<details>
<summary><strong>Phase 5: Chat and Query Interface</strong></summary>


**Goal:** Add a **user-facing query layer** over the same backend intelligence APIs.

**Key outputs:**

- **Initial chat/search frontend.**
- **Entity context views.**
- **Match review experience.**
- **Approval queue.**
- **Feedback collection.**
- **Basic user permissions.**

**Dependencies:**

- Stable retrieval and matching endpoints.
- Guardrails and structured output validation.
- User roles and access rules.

**Why this comes here:** **A chat UI is most useful once retrieval, evidence, and action proposals are already reliable.**


</details>

<details>
<summary><strong>Phase 6: Analytics, Forecasting, and Optimisation</strong></summary>


**Goal:** Add **analytical and forecasting capabilities** after operational data is flowing through the system.

**Key outputs:**

- **Curated analytics views.**
- **KPI dashboards.**
- **Funnel and conversion tracking.**
- **Market/skill trend analysis.**
- **Source quality analysis.**
- **Forecasting experiments.**
- **Resource allocation recommendations.**

**Dependencies:**

- Stable canonical data and event history.
- Clear KPI definitions.
- Sufficient volume and quality of outcome data.

**Why this comes here:** **Analytics and forecasting need clean historical data.** Building dashboards before data quality and event capture are stable risks producing misleading outputs.


</details>

</details>
<details>
<summary><strong>7. Recommended Phase 1 Scope</strong></summary>


Phase 1 should be **deliberately narrow**. The purpose is to establish the **platform foundation** and prove **one or two core business workflows**, not to replace every tool.

Recommended Phase 1 scope:

- **Core Supabase schema** for companies, people, candidates, contacts, jobs, skills, documents, interactions, source records, and relationship tables.
- **Raw source record storage and provenance tracking.**
- **Initial document chunking and embedding design** for CVs, job specs, notes, and relevant source text.
- **Initial canonical identity rules** for people, companies, jobs, and skills.
- **A small set of REST endpoints:**
  - Ingest source record.
  - Upsert company/person/job.
  - Attach document or document metadata.
  - Search entity context.
  - Request candidate/job match.
  - Submit match feedback.
  - Create proposed workflow action.
- **Initial GraphRAG retrieval capability** that combines:
  - Skill matching.
  - Candidate/job relationships.
  - Company/contact relationships.
  - Document chunk retrieval.
  - Interaction history where available.
- **Initial Make.com integration points:**
  - Trigger ingestion from a selected source or export.
  - Send match results to Slack, task system, or email draft workflow.
  - Capture approval/feedback and send it back to the backend.
- **Initial evaluation harness:**
  - Deterministic schema checks.
  - Structured output validation.
  - Retrieval fixture tests.
  - A small labelled matching dataset.
  - Action-safety checks.
- **GitHub Actions CI checks and Vercel deployment workflow.**

Recommended Phase 1 exclusions:

- Full production chat UI.
- Broad two-way sync across all systems.
- Fully autonomous outreach.
- Deep analytics/dashboarding.
- Advanced ML training.
- Complete historical migration.
- Multi-agent workflow complexity beyond the minimum needed for retrieval and action proposal.


</details>
<details>
<summary><strong>8. Data Modelling Recommendations</strong></summary>


The data model should use **Supabase/Postgres as a graph-like relational system** rather than introducing a separate graph database prematurely.

<details>
<summary><strong>Core Pattern</strong></summary>


Use:

- **Canonical entity tables** for stable business objects.
- **Link tables** for relationships between entities.
- **Source-system record tables** for raw and mapped external records.
- **Document tables** for files, metadata, and extracted text.
- **Chunk tables** for retrievable text units.
- **Embedding columns** for semantic search.
- **Audit tables** for state changes, sync runs, match decisions, and action execution.
- **Feedback tables** for recruiter judgements and downstream outcomes.


</details>

<details>
<summary><strong>Example Relationship Types</strong></summary>


- Candidate has skill.
- Candidate worked at company.
- Candidate is also contact or hiring manager.
- Hiring manager works at company.
- Job requires skill.
- Job belongs to company.
- Interaction involves person, company, job, or document.
- Document describes candidate, job, company, or interaction.
- Source record maps to canonical entity.
- Outreach action targets person or company.


</details>

<details>
<summary><strong>Source-of-Truth Strategy</strong></summary>


Each canonical field should have a **source-of-truth rule**. For example:

- **Email addresses** may be sourced from CRM/ATS, Outlook, LinkedIn exports, or manual update, but **confidence and recency** should decide which value is primary.
- **Candidate CV text** should preserve the original document and extracted text, not just the LLM summary.
- **Skills** should be normalised into a canonical vocabulary, while preserving source phrases.
- **Job status** should have an explicit authoritative source per workflow.
- **System-generated recommendations** should not overwrite human-confirmed canonical data without review.


</details>

<details>
<summary><strong>Deduplication and Entity Resolution</strong></summary>


**Entity resolution is a major workstream, not a minor cleanup task.**

Recommended signals:

- Email address.
- Phone number.
- LinkedIn profile URL or public identifier where legally usable.
- Company domain.
- Person name plus company plus role.
- CV document fingerprints.
- Source-system IDs.
- Interaction history.
- Skill and employment overlap.

The model should support **confidence scores, merge decisions, split decisions, and manual override history**.


</details>

<details>
<summary><strong>Auditability and Provenance</strong></summary>


Every **derived recommendation** should be traceable to:

- **Source records.**
- **Canonical entities.**
- **Retrieved documents or chunks.**
- **Relationship traversal path.**
- **Model provider and model version.**
- **Prompt or workflow version.**
- **Ranking/scoring version.**
- **User feedback or approval status.**

Without **provenance**, the system will be difficult to debug, evaluate, and trust.


</details>

</details>
<details>
<summary><strong>9. Make.com Integration Guidance</strong></summary>


Make.com should be used as the **external workflow orchestration and action execution layer**.

Recommended uses:

- Listen for **changes in active systems** where native APIs or triggers are available.
- **Poll or schedule ingestion jobs** for sources that lack good webhooks.
- Send **source-system payloads** to backend ingestion endpoints.
- Receive **structured match results, action proposals, and status responses** from the backend.
- Execute **approved actions** in external tools:
  - Create or update CRM/ATS records.
  - Create Asana tasks.
  - Send Slack notifications.
  - Draft emails.
  - Start outreach sequences.
  - Update spreadsheets where still required.
  - Trigger dashboard refreshes.
- Route **approval decisions** back to the backend.
- Handle **simple retries and operational notifications**.

Make.com should not:

- Own **canonical identity**.
- Store the **master record** of candidates, companies, jobs, skills, or interactions.
- Implement **matching or ranking logic**.
- Own **prompt templates or LLM reasoning**.
- Make **final decisions on high-impact actions** without backend guardrails and human approval.
- Become the place where **business-critical logic** is hidden across many scenarios.

Practical Make.com design rules:

- Treat **backend APIs as the contract**.
- Keep payloads **structured and versioned**.
- Use **idempotency keys** for event ingestion.
- Log **scenario run IDs** back into Supabase.
- Prefer **human approval** for outreach, CRM mutation, and contact enrichment during early phases.
- Keep **transformations simple**; complex mapping belongs in the backend.
- Use Make.com to **reduce integration time**, not to replace software architecture.


</details>
<details>
<summary><strong>10. LangChain v1 and LangGraph Guidance</strong></summary>


**LangChain v1** should be used for **model and tool abstraction** inside the backend. It should help standardise calls to model providers, retrievers, structured output parsers, and tool interfaces.

**LangGraph** should be used for **stateful or multi-step workflows** where the system needs durable control over:

- **Retrieval planning.**
- **Entity context assembly.**
- **Candidate/job matching.**
- **Tool selection.**
- **Human approval checkpoints.**
- **Retry and fallback paths.**
- **Action proposal generation.**
- **Long-running workflow state.**

Recommended conceptual pattern:

- The backend receives a **business request**.
- The backend resolves relevant **canonical entities and permissions**.
- LangGraph coordinates **retrieval, scoring, LLM reasoning, and action planning**.
- LangChain abstractions call the selected **model provider and tools**.
- The backend validates **structured outputs**.
- The backend stores **evidence, decisions, and proposed actions**.
- Make.com executes only the **approved external actions**.

**Tool calling should be controlled.** Tools should have explicit permissions, typed inputs, typed outputs, audit logging, and approval requirements for high-impact actions.

Avoid early overuse of **agent autonomy**. The first useful version should behave more like a **grounded workflow engine with LLM reasoning** than an unconstrained agent.


</details>
<details>
<summary><strong>11. LLM Evaluation Strategy</strong></summary>


**Evaluation must be included from the beginning.** The system will be judged on whether it retrieves the right evidence, ranks useful matches, explains recommendations accurately, and avoids unsafe actions.

<details>
<summary><strong>Deterministic Checks</strong></summary>


- **API response schema validation.**
- **Required field validation.**
- **Entity ID and relationship integrity checks.**
- **Idempotency checks** for repeated ingestion events.
- **Permission checks** for action proposals.
- **Regression tests** for known mapping rules.


</details>

<details>
<summary><strong>Structured Output Validation</strong></summary>


- Validate **LLM responses against strict schemas**.
- Reject responses that omit **required evidence**.
- Reject **malformed action proposals**.
- Enforce **allowed action types**.
- Validate **confidence, rationale, and evidence references**.


</details>

<details>
<summary><strong>Groundedness and Hallucination Checks</strong></summary>


- Require every recommendation to reference **retrieved evidence**.
- Detect **claims not supported** by retrieved chunks or structured records.
- Compare generated summaries against **source excerpts**.
- Flag recommendations with **weak or missing evidence** for human review.


</details>

<details>
<summary><strong>Retrieval Quality Checks</strong></summary>


- Maintain a **small fixture set** of known jobs, candidates, companies, and skills.
- Measure whether **expected entities appear in top-k results**.
- Track **precision and recall** for known retrieval cases.
- Test **graph traversal** separately from semantic retrieval.
- Test **combined retrieval** against realistic recruitment prompts.


</details>

<details>
<summary><strong>Ranking and Matching Quality Checks</strong></summary>


- Build a **labelled dataset** from recruiter feedback and historical outcomes.
- Track **top-k match quality**.
- Track **explanation usefulness**.
- Track **false positives and false negatives**.
- Capture whether accepted recommendations later produced **meaningful outcomes**.


</details>

<details>
<summary><strong>Action-Safety and Permission Checks</strong></summary>


- Ensure **risky actions require approval**.
- Ensure **draft content is labelled as draft**.
- Ensure **external writes are disabled** in evaluation and test environments.
- Ensure tools cannot mutate records without **explicit allowed action types**.
- Ensure Make.com scenarios cannot **bypass backend approval requirements**.


</details>

<details>
<summary><strong>CI-Based Evaluation</strong></summary>


**GitHub Actions** should run a practical evaluation suite on **pull requests and before deployment**:

- **Unit and integration tests.**
- **Schema and contract checks.**
- **Retrieval fixture tests.**
- **Structured LLM output checks** using fixed test cases.
- **Prompt/workflow regression tests.**
- **Safety and permission tests.**

**LLM evaluations should start small** and become more formal as real feedback and outcomes accumulate.


</details>

</details>
<details>
<summary><strong>12. CI/CD Recommendations</strong></summary>


The project should use **GitHub as the source of truth** for implementation artifacts.

Recommended CI/CD setup:

- **GitHub repository with branch protection.**
- **Pull request workflow** for all production changes.
- **GitHub Actions** for linting, tests, type checks, evaluation checks, and documentation checks.
- **Vercel deployment** for backend preview and production environments.
- **Supabase migrations tracked in source control.**
- **Separate development, preview/staging, and production environments** where practical.
- **Environment variables managed through Vercel and Supabase secret management**, not committed to the repository.
- **CI checks** for missing environment variable documentation.
- **CI checks** for API contract changes where possible.
- **Deployment gates** for failing evaluations.

Recommended pipeline shape:

```mermaid
graph LR
    Dev[Developer branch]
    PR[Pull request]
    CI[GitHub Actions]
    Preview[Vercel preview deployment]
    Review[Engineering review]
    Main[Main branch]
    ProdCI[Production checks]
    Prod[Vercel production deployment]
    Monitor[Logs, eval telemetry, and feedback]

    Dev --> PR
    PR --> CI
    CI --> Preview
    Preview --> Review
    Review --> Main
    Main --> ProdCI
    ProdCI --> Prod
    Prod --> Monitor
```

**Deployment should not be treated as complete** unless evaluation and operational telemetry are also considered.


</details>
<details>
<summary><strong>13. Risks, Pitfalls, and Common Failure Modes</strong></summary>


- **Making Make.com the brain:** Make.com is useful for integration and action execution, but it will become hard to test, version, and reason about if it owns intelligence or canonical business logic.
- **Underestimating entity resolution:** Duplicate candidates, contacts, companies, and jobs will undermine matching quality unless identity rules and merge workflows are treated as core architecture.
- **No source-of-truth rules:** If the system cannot decide which source wins for a field, two-way sync will create conflicts and data decay.
- **Weak provenance:** Recommendations without traceable evidence will be hard to trust, evaluate, or debug.
- **Overbuilding agent autonomy too early:** Autonomous agents should not be allowed to execute outreach, CRM mutation, or data enrichment until retrieval, evaluation, and approval controls are mature.
- **Mistaking vector search for GraphRAG:** pgvector search over chunks is useful, but GraphRAG requires structured relationship traversal and entity-aware retrieval.
- **Trying to integrate everything at once:** The tool list is large. A phased approach is required to avoid a brittle integration mesh.
- **Poor evaluation discipline:** Without test fixtures and outcome tracking, prompt changes and model changes will create silent regressions.
- **Unclear legal constraints:** LinkedIn-derived data, scraping workflows, and automated profile refreshes may carry platform, contractual, or compliance risks.
- **Over-trusting raw legacy data:** Legacy CRMs, spreadsheets, and document stores may contain stale, duplicated, or contradictory records.
- **Letting summaries replace source documents:** LLM summaries are useful but should not replace original documents, extracted text, or evidence references.
- **Ignoring operational failure modes:** Sync retries, partial failures, duplicate events, and rate limits must be designed into the integration layer.
- **Premature analytics:** Forecasting and dashboards will be misleading if the underlying event, outcome, and source data are not clean.


</details>
<details>
<summary><strong>14. Open Questions and Decisions to Resolve</strong></summary>


Before implementation begins, the team should resolve:

- Which systems are definitely **legacy** and should be migrated or retired?
- Which **active systems** must remain operational in the first six months?
- Which system, if any, remains the **operational CRM/ATS** during early phases?
- What is the **first priority workflow**: job-to-candidate matching, company lead generation, hiring-manager discovery, CV ingestion, or outreach support?
- Which data sources are available via **API, export, webhook, or manual upload**?
- What **legal and platform constraints** apply to LinkedIn, LinkedHelper, scraped data, and third-party datasets?
- What fields are considered **sensitive or restricted**?
- What **user roles and approval permissions** are required?
- Which **model provider** should be used first for cost, quality, privacy, and reliability?
- What is the expected **latency** for matching and retrieval workflows?
- What **volume of CVs, emails, interactions, and source records** should the system expect initially?
- What is the **canonical skills taxonomy strategy**?
- What is the **merge/split process** for duplicate people and companies?
- What **actions are allowed automatically, which require approval, and which are out of scope**?
- What are the first **evaluation fixtures and success metrics**?
- What systems should **Make.com write back to** in the first production workflow?
- What data needs to be available for future **Power BI or dashboard reporting**?


</details>
<details>
<summary><strong>15. Recommended Next Documents</strong></summary>


After this North Star document, the next planning artifacts should be:

- **Domain model document:** Canonical entities, fields, relationship types, identity rules, and source-of-truth policy.
- **Source systems inventory and migration map:** Legacy systems, active systems, access method, export format, API availability, ownership, and priority.
- **API contract draft:** REST endpoints, payloads, response schemas, idempotency strategy, error conventions, and versioning.
- **Make.com workflow inventory:** Candidate scenarios, trigger systems, action systems, approval points, retries, and logging requirements.
- **Evaluation plan:** Test fixtures, labelled examples, retrieval metrics, ranking metrics, structured output checks, and CI evaluation gates.
- **Implementation roadmap:** Sequenced delivery plan with milestones, dependencies, owners, and release criteria.
- **Security and permissions document:** Data sensitivity, user roles, row-level security approach, audit logging, approval model, and external action permissions.
- **Entity resolution strategy:** Deduplication signals, confidence scoring, merge/split process, human review flow, and conflict resolution.
- **Data provenance and audit specification:** How source records, generated outputs, model calls, approvals, and external actions are traced.
- **Analytics roadmap:** KPI definitions, reporting views, dashboard requirements, forecasting candidates, and data readiness criteria.


</details>
<details>
<summary><strong>16. Baseline Design Position</strong></summary>


The baseline design position is:

- **Supabase is the central data and memory layer.**
- **Vercel backend services own intelligence, data modelling, retrieval, matching, evaluation, and guardrails.**
- **Make.com connects the backend to the operational stack and executes approved actions.**
- **LangChain v1 and LangGraph power controlled backend reasoning workflows.**
- **GraphRAG combines relational graph traversal, semantic retrieval, evidence assembly, and structured LLM reasoning.**
- **Evaluation and CI/CD are first-class project concerns, not later polish.**
- **Phase 1 should prove a narrow, useful workflow with strong foundations** before broader automation, chat, analytics, or autonomy.

</details>
