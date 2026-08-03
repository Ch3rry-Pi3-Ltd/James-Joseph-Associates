# Phase 1 To-Do List

<details open>
<summary><strong>Current Outstanding Program Work (1 August 2026)</strong></summary>

This is the trimmed engineering backlog that matters most right now, in the
latest agreed priority order.

### Current Delivery Sequence

The active engineering sequence below excludes work that requires Tom's input,
workspace-owner access, commercial decisions, or DNS control. Those items are
kept in a separate deferred lane so they do not block independent delivery.

#### Completed in this delivery

- [x] Add a side-by-side shortlist candidate comparison.
- [x] Surface clear recent-employment and structured skills evidence in the
  comparison and candidate profile views.

#### Immediate UI priorities, in agreed order

- [x] Make CV-backed, profile-only, and cross-source indicators clearer across
  search, shortlist, comparison, profile preview, and shared-shortlist views.
- [x] Surface source provenance and evidence freshness more clearly across
  search, shortlist, comparison, profile preview, and shared-shortlist views.
- [x] Make candidate contact routes easier to inspect and use through a private
  preview panel with email, phone, LinkedIn, copy actions, and last-contact context.
- [x] Improve the presentation of evidence-backed strengths and gaps to clarify
  across comparison, detailed shortlist, and shared-shortlist views.
- [x] Add a cleaner pre-export review step covering the role title and brief,
  ranked candidates, evidence categories, CV availability, strengths, gaps, and
  explicit recruiter confirmations before package generation.

#### Following engineering priorities, in order

- [x] Instrument and improve performance across Review, Company, search, and
  shortlist flows.
- [x] Remove repeated database queries and avoidable API calls.
- [x] Build automated regression, groundedness, stability, and sensitive-data
  checks that do not depend on recruiter labels:
  - [x] benchmark full-text, semantic, hybrid, and graph-assisted retrieval as
    separate stages so each layer earns its latency and complexity
  - [x] document and test embedding-model objectives, chunking choices, and
    structured-block boundaries against representative recruitment queries
  - [x] build a RAG failure matrix covering missing, stale, conflicting, noisy,
    or malicious evidence, provider timeouts, and malformed structured outputs
  - [x] require every generated strength, gap, summary, and recommendation to
    map to retrievable evidence
  - [x] automate groundedness, stability, schema, and sensitive-data checks
    independently of recruiter-labelled relevance judgements
  - [x] test MCP authentication, tool boundaries, permissions, timeouts, rate
    limits, and failure responses independently of workspace publication
- [x] Finish Recruitly jobs, opportunities, and journal/note ingestion using
  existing access:
  - [x] persist all `4` jobs currently returned by Recruitly and verify all
    `4` source records link one-to-one to canonical `jobs`
  - [x] sweep opportunities and record the verified empty source result
    (`0` records returned on 2 August 2026)
  - [x] sweep journals for all returned jobs and opportunities and record the
    verified empty source result (`0` journal entries returned)
  - [x] retain the idempotent bulk runner and compact live audit artifact for
    future source refreshes
- [x] Build and test the database export and restore path:
  - [x] export `public` data separately from the tracked migration-owned schema
  - [x] checksum archives and record migration fingerprints plus exact table counts
  - [x] require a distinct, empty, explicitly confirmed restore target
  - [x] restore atomically and verify all post-restore table counts
  - [x] exercise the real path against disposable PostgreSQL 17/pgvector source
    and target databases using all tracked migrations and synthetic data
- [ ] Harden API rate limiting, caching, Content Security Policy, and database
  permissions:
  - [x] add a shared database-backed per-principal rate limit for the main API,
    keep health checks exempt, fail closed when the control store is unavailable,
    and prevent private API responses from being cached by browsers or CDNs;
    activation is gated until migration `0014` is explicitly applied
  - [x] add short, bounded warm-instance caching for the stable company directory
    and review overview reads without treating serverless memory as durable state
  - [x] enforce a per-request nonce Content Security Policy through the installed
    Clerk/Next.js middleware contract, including explicit object, base, framing,
    image, font, and worker boundaries
  - [x] add migration-owned read-only and writer database roles, remove public
    schema-create access, and grant least-privilege current/default table and
    sequence permissions; runtime credential membership remains a deployment step
  - [x] inventory context-window, token, truncation, latency, and cost budgets
    for every model-backed workflow in `docs/llm_operational_budgets.md`
  - [ ] measure end-to-end model latency and, where streaming/provider telemetry
    permits, time to first token, inter-token latency, token throughput, queue
    time, and prompt/prefill versus generation/decode time
  - [ ] benchmark representative short and long prompts, output limits, and
    concurrency so latency and cost regressions are visible
  - [ ] evaluate provider prompt caching for repeated system instructions and
    stable retrieval context, including cache-hit, latency, and cost effects
  - [ ] add stage-level observability for latency, token usage, cost, model and
    prompt versions, retrieval inputs, and run identifiers
  - [ ] exercise retries, fallbacks, idempotency, caching, background jobs, and
    load behaviour
  - [ ] record architecture decisions for RAG versus fine-tuning and for
    bounded workflows versus multi-agent designs before adding either complexity
  - [ ] define a self-hosted inference decision gate based on privacy, workload,
    latency, cost, scale, and provider-dependency evidence
  - [ ] only if that gate is met, benchmark a representative workload across a
    suitable engine such as vLLM, SGLang, or llama.cpp and document the relevant
    hardware, quantization, KV-cache, attention, batching, and parallelism choices
- [ ] Reconcile outdated documentation, environment-variable contracts, and
  checklist statuses.

All immediate UI work and the engineering tasks above can proceed without Tom.
Recruiter-labelled relevance, disagreement resolution, and final usefulness
approval remain in the deferred lane below.

#### Deferred pending Tom or another external owner

- [ ] Recruiter-labelled UAT, known-strong-candidate identification, and final
  shortlist-quality approval.
- [ ] ChatGPT Business workspace publication and workspace-user validation.
- [ ] LinkedHelper chat/message privacy and retention decisions.
- [ ] Supabase ownership, billing, and future client-owned infrastructure decisions.
- [ ] DNS-backed production domain and Clerk production-instance cutover.
- [ ] Approval policy for any future write-capable agent or integration actions.

### Delivery Reporting

- [x] Create a reusable CH3RRY PI3 weekly development-report pack with:
  - [x] commit-backed reporting-window evidence
  - [x] verified implementation metrics and business benefits
  - [x] explicit alignment to the North Star architecture
  - [x] a justified next-week milestone and delivery boundary
  - [x] branded, editable HTML and validated 3-4 page PDF output
- [ ] Produce the report at the end of each delivery week and reconcile its
  next milestone with this priority list.

- [x] Add the conversational operator foundation:
  - [x] grounded answers over canonical candidates, companies, contacts, jobs,
    opportunities, and past interactions
  - [x] bounded per-user conversation memory with a 12-hour TTL and four-turn ceiling
  - [x] remote stateless Streamable HTTP MCP endpoint at `/mcp`
  - [x] read-only tools for candidate search/profile/CV references, company
    context, company directory, and candidate-to-company lead discovery
  - [x] dedicated bearer authentication, DNS-rebinding protection, shared
    database-backed rate limiting, and metadata-only audit logging
- [ ] Complete ChatGPT Business workspace rollout:
  - [ ] Prepare and send the workspace owner a short connection guide covering
    the exact ChatGPT Business setup steps below.
  - [ ] Confirm the person completing setup is an Admin or Owner of the intended
    ChatGPT Business workspace; members cannot publish custom MCP apps.
  - [ ] In ChatGPT web, enable Developer mode for that admin account from
    Workspace settings -> Apps -> Create, or User settings -> Apps ->
    Advanced settings.
  - [ ] Create a custom MCP app using the production endpoint:
    `https://james-joseph-associates.vercel.app/mcp`.
  - [ ] Select the supported authentication mechanism:
    - [ ] use the existing dedicated bearer credential if ChatGPT offers that
      option during app creation
    - [ ] otherwise implement OAuth before connecting it; never publish the
      endpoint without authentication
    - [ ] transfer the required credential through a secure channel rather
      than WhatsApp, email, screenshots, or documentation
  - [ ] Run **Scan tools** and confirm only the six intended bounded read-only
    recruitment tools are exposed.
  - [ ] Create the app as a draft and test it before publication:
    - [ ] search candidates from a realistic role brief
    - [ ] retrieve one candidate profile and its CV reference
    - [ ] retrieve company, contact, job, opportunity, and interaction context
    - [ ] confirm out-of-scope requests cannot run raw SQL, inspect arbitrary
      tables, write records, delete data, send outreach, or modify Recruitly
  - [ ] Publish the vetted app from Workspace settings -> Apps -> Drafts.
  - [ ] Confirm which workspace users can access it; keep the first rollout to
    the approved operator accounts only where Business workspace controls
    permit.
  - [ ] Confirm users can start a normal ChatGPT conversation, select the
    custom app, and ask grounded recruitment questions without direct
    Supabase credentials or database access.
  - [ ] Run and record the documented recruiter UAT prompts, returned evidence,
    CV retrieval, failure cases, and response times.
  - [ ] Add an operator note explaining that Business workspaces use a frozen
    snapshot of approved MCP tools; material tool changes require review and
    republishing rather than appearing automatically.
  - [ ] Document token rotation, app recreation/republishing, access removal,
    audit review, and incident-disable procedures.
  - [ ] Keep the initial release read-only; define a separate controlled rollout
    for explicitly approved write actions later.
- [x] Polish the `/match` UI for UAT:
  - [x] clearer instructions
  - [x] more intuitive flow labels
  - [x] more professional presentation of search, shortlist, and company evidence
- [ ] Continue retrieval quality work:
  - [x] first four-role real-brief retrieval and shortlist benchmark
  - [x] tune profile-only evidence handling based on benchmark findings:
    bounded headline, summary, current-role, location and skill evidence now
    reaches reranking without contact details; the exact re-run promoted one
    Linked Helper-only profile into a final top-five list
  - [ ] recruiter-labelled real-brief search tuning
  - [ ] recruiter-validated shortlist quality checks
  - [ ] better evidence presentation for recruiter trust
- [ ] Build a repeatable recruiter-quality and AI-workflow evaluation harness:
  - [x] add the first versioned four-role brief fixture, compact JSON artifact,
    source-mix audit, previous-shortlist comparison, and written findings
  - [ ] create a versioned set of real role briefs with recruiter-labelled
    relevant, borderline, and unsuitable candidates
  - [ ] measure first-pass retrieval with recall at the shortlist-pool cutoff,
    reciprocal rank, and ranking quality rather than text-generation metrics
    such as BLEU or ROUGE
  - [ ] measure final-shortlist precision, ordering, evidence coverage, and
    whether known strong candidates were missed
  - [ ] capture structured recruiter UAT feedback and promote reviewed examples
    into regression fixtures
  - [ ] use LLM-as-judge only as a secondary, rubric-based check alongside
    deterministic checks and human review
  - [x] add groundedness, unsupported-claim, sensitive-data, authentication,
    and future write-action safety tests
  - [ ] add trajectory and stop-condition evaluations when LangGraph workflows
    begin using multi-step loops
- [ ] Performance and scalability hardening:
  - [x] record response times and database timings for the Review, Company,
    Match search, and Match shortlist workflows
  - [x] identify and remove repeated database queries and avoidable API round
    trips
  - [ ] batch high-volume database reads and writes where this preserves
    reconciliation, provenance, and audit guarantees
  - [ ] add selective caching for stable or slow-changing data such as company
    directories, dashboard counts, and bounded lookup results
  - [ ] inspect slow SQL with query plans and add only evidence-backed indexes,
    accounting for their Supabase storage cost
  - [ ] move long-running imports, embedding backfills, and other bulk work into
    background jobs with progress reporting, safe retries, and idempotency
  - [ ] add performance regression checks for the main operator workflows
- [x] Add operator output tools:
  - [x] downloadable Word shortlist plus retrievable CV ZIP package
  - [x] authenticated, expiring, revocable shortlist links
  - [x] private saved role briefs with retrieval settings, target-company
    context, and latest search/shortlist snapshots
  - [x] shortlist feedback capture
- [ ] Harden LinkedHelper ingestion:
  - [x] CSV import normalizer
  - [x] inspect and compare the two Dropbox `.lhd2` backups without extracting
    them to disk
  - [x] confirm the July 2026 backup is a strict data superset of the older
    backup
  - [x] native in-memory `.lhd2` backup-to-canonical person payload mapper
  - [x] deterministic matching to existing canonical people through provenance,
    LinkedIn profile, email, phone, and unique name-plus-company keys
  - [x] deterministic company reconciliation using provenance, LinkedIn
    organisation identity, domain, and unambiguous company name
  - [x] provenance tracking
  - [x] read-only dry-run reports separating matched, new, ambiguous, and
    skipped people and companies before any bulk write
  - [x] production-proof a bounded import of 20 new profiles with current
    roles, employment history, skills, connection metadata, and exact
    provenance-link audits
  - [x] add a restartable native-backup batch runner with one transaction per
    batch, exact post-write provenance audits, an ignored local checkpoint,
    and a conservative database-size ceiling
  - [x] production-proof the restartable runner through source offset 200
    across ten audited batches
  - [x] complete a further controlled run of 1,000 source profiles through
    offset 1,400 with exact audits and storage monitoring
  - [x] complete a further controlled run of 3,000 source profiles through
    offset 4,400 with exact audits and storage monitoring
  - [x] complete the next controlled run of 3,000 source profiles through
    offset 7,400 with exact audits and storage monitoring
  - [x] complete the remaining 3,462 native-backup profiles through final
    offset 10,862 with exact audits and storage monitoring
  - [x] complete semantic coverage across the resulting searchable canonical
    candidate corpus
  - [ ] decide privacy and retention rules before importing chats/messages as
    canonical interactions
  - [ ] webhook path if payload support is good enough
- [x] Finish Recruitly canonical ingest beyond people/contacts/companies:
  - [x] jobs (`4` live source rows persisted and canonically linked)
  - [x] opportunities (ingestion path verified; live source currently returns `0`)
  - [x] journal / note interactions (all available job/opportunity journals
    swept; live source currently returns `0`)
- [ ] Keep Supabase service live while ownership/billing is sorted.
- [x] Write and verify a controlled database export / migration path into a
  future owner-controlled setup; the transfer runner is ready independently,
  while actual target provisioning and ownership remain externally deferred.
- [ ] Complete production auth cutover:
  - [ ] Tom to provide/control a real DNS-backed subdomain for the app
    (recommended: `app.jamesjosephassociates.co.uk`)
  - [ ] Add the custom domain to Vercel and point DNS correctly
  - [ ] Create the Clerk production instance against that real domain
  - [ ] Replace Clerk test keys in Vercel with `pk_live_...` and `sk_live_...`
  - [ ] Verify first-time sign-in and protected-route behavior on the real domain

</details>

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

Checkpoint note:

- [x] Record the current cross-source state in
  `docs/source_integration_checkpoint_2026-05-20.md` so the current working
  model and proof points are not trapped in chat history.

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
  - [x] Inspect a 20-30 file sample and record matching/source-shape findings.
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
    - [x] Preserve vacancy-code (`tw...`) metadata for advert-response folders.
    - [x] Decide whether advert-response Dropbox CVs should be modelled as:
      - [ ] document-first candidate evidence
      - [x] vacancy-aware applications
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
    - [x] Confirm Microsoft app registration ownership and live app credentials.
    - [x] Confirm whether the first mailbox read should target Tom directly or a delegated/shared mailbox path.
      - [x] first live proof used Tom's own mailbox successfully
      - [ ] delegated/shared mailbox path still to be tested separately if needed
    - [x] Inspect a first mailbox folder sample and record attachment/source-shape findings.
      - [x] root Inbox proved too large for naive first-page preview (`504` from Graph on the broad Inbox read)
      - [x] first narrow Outlook advert-response path identified:
        - [x] `Inbox`
        - [x] `# ADV-CVR`
        - [x] `### DOMINIQUE FOLDER`
        - [x] `tw394`
        - [x] `tw396`
        - [x] `tw397`
        - [x] `tw398`
        - [x] `tw399`
      - [x] `# ADV-CVR` root folder already contains mixed advert-response traffic:
        - [x] CV-Library application emails
        - [x] Totaljobs "Suitable application" emails
        - [x] messages with attachments visible through Graph
      - [x] `tw394` Outlook folder is a clean first candidate for narrow ingestion:
        - [x] vacancy code visible in message subjects
        - [x] sender email visible
        - [x] received timestamp visible
        - [x] `hasAttachments = true` on sampled messages
      - [x] one real Outlook attachment-list proof succeeded for a Totaljobs advert-response message
      - [x] add a narrow Outlook attachment download/read helper for the first real mailbox-ingestion slice
      - [x] prove one real Outlook attachment can feed the resume extraction pipeline end to end:
        - [x] source folder `# ADV-CVR > ### DOMINIQUE FOLDER > tw394`
        - [x] sample message subject:
          `sulaimanalikhan710@gmail.com - Totaljobs - Suitable application for Junior Desktop Engineer - Hedge Fund tw394`
        - [x] sample file:
          `SULAIMAN MOHAMMED (... - Totaljobs).pdf`
        - [x] extractor = `pypdf`
        - [x] extracted character count = `6185`
      - [x] move from proof-only reads into the first narrow Outlook ingestion path:
        - [x] add child-folder Graph helper so the mailbox path can be resolved by folder name instead of a hard-coded folder ID
        - [x] add narrow Outlook resume persistence helpers:
          - [x] Outlook message provenance `source_record`
          - [x] Outlook attachment provenance `source_record`
          - [x] canonical `documents` row with `document_type = resume`
          - [x] `source_record_links`
          - [x] optional job link by `tw...` code when a canonical job already exists
        - [x] add the operator script:
          - [x] `scripts/persist_outlook_tw394_folder.py`
        - [x] run the first live `tw394` ingestion proof:
          - [x] resolved mailbox path:
            `Inbox > # ADV-CVR > ### DOMINIQUE FOLDER > tw394`
          - [x] scanned first `10` messages
          - [x] ingested first supported attachment successfully
          - [x] canonical `document_id = 5cc458b8-e02e-4418-962c-fabaf5faeb66`
          - [x] initial `resolved_job_id = null` was expected before the canonical
            `tw394` job existed
        - [x] persist the canonical `tw394` job/spec side:
          - [x] JobAdder job `891841`
          - [x] canonical `job_id = 8279afc7-6525-4fc7-bb3a-e6e8ffb82b35`
          - [x] Dropbox job-spec PDF:
            `/NEW Dropbox/# DLV/LIVE JOBS - [Job Specs]/tw394 - GSAcapital - Technical Support/GSA Capital - INFRA-Technical Support -2026.pdf`
          - [x] canonical job-spec `document_id = 8222d726-ee80-4c38-951f-02d5dc7dae34`
        - [x] rerun the Outlook `tw394` ingest after persisting the canonical job:
          - [x] same Outlook resume `document_id` reused:
            `5cc458b8-e02e-4418-962c-fabaf5faeb66`
          - [x] `resolved_job_id = 8279afc7-6525-4fc7-bb3a-e6e8ffb82b35`
          - [x] advert-response job linking by `tw...` is now proven live for `tw394`
      - [x] generalize the narrow Outlook folder ingestor into a reusable operator entrypoint:
        - [x] add a generic script entrypoint for arbitrary Outlook folder paths
        - [x] keep the older `tw394` operator entrypoint as a compatibility wrapper
      - [ ] add the next Outlook mailbox-ingest automation layer:
        - [ ] derive Dropbox export subfolders from Outlook `receivedDateTime`
          such as `year / quarter`
        - [ ] add rolling date-window mailbox backfill so older advert-response
          CVs can be stepped through in controlled batches
        - [ ] decide whether Outlook CVs should land directly in Supabase only,
          or be mirrored into Dropbox first and then ingested from there
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
    - [x] check whether vacancy codes or job-ad references can anchor
      Dropbox/Outlook advert-response CVs
    - [x] decide whether JobAdder should be the structured system of record for
      advert-response/application context
    - [x] inspect whether advert-response CVs sit on JobAdder applications or
      on JobAdder candidates:
      - [x] sample `tw398` applications have zero application attachments
      - [x] sample `tw398` candidates each have one resume attachment
      - [x] Dropbox `tw398` search shows:
        - [x] job-spec folder
        - [x] archive `.eml` files
        - [x] duplicate CV files in archive / IN-JAD areas
      - [x] parse one real `tw398` Dropbox `.eml` file to confirm what the
        advert-response archive actually preserves:
        - [x] source channel (`Totaljobs`)
        - [x] destination mailbox (`tom.owens@...`)
        - [x] received timestamp
        - [x] vacancy code (`tw398`)
        - [x] candidate-specific attachment filename
      - [x] compare one real JobAdder candidate attachment against the
        matching Dropbox CV copy:
        - [x] first proof pair completed:
          - [x] candidate `17071060`
          - [x] attachment `21562882`
          - [x] Dropbox file `/#################----CV's- IN-JAD-JobAdder/sanjeev sadha.docx`
          - [x] filename match
          - [x] byte size match
          - [x] SHA-256 match
        - [x] second proof pair completed from `ACHTUNG! in RFL!`:
          - [x] candidate `17068569`
          - [x] attachment `21558363`
          - [x] Dropbox file `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/Zafar_Lead_Finance.docx`
          - [x] filename match
          - [x] byte size match
          - [x] SHA-256 match
      - [ ] extract text comparison only if a later pair differs by hash
      - [ ] Add a narrow live JobAdder job-detail preview for the linked role:
        - [x] fetch `GET /jobs/{jobId}` for `jobId = 936462`
        - [x] confirm that the live JobAdder job record aligns with the
          Dropbox `tw398` job-spec area:
          - [x] `jobTitle = tw398 - KDB Developer`
          - [x] company = `B2C2`
          - [x] full HTML `jobDescription` present in JobAdder
          - [x] JobAdder job description materially overlaps the Dropbox PDF
            `B2C2 - Snr. KDB Developer - London - 2026.pdf`
        - [x] compare the JobAdder job record with the Dropbox job-spec folder
          `tw398 - B2C2 - KDB Developer x2`
        - [x] decide the first narrow persistence shape for job specs in
          Supabase:
          - [x] JobAdder job -> canonical `jobs` row
          - [x] Dropbox job-spec PDF -> canonical `documents` row with
            `document_type = job_spec`
          - [x] provenance-bearing `source_records`
          - [x] `source_record_links`
          - [x] `document_links` with `relationship_type = job_spec`
        - [x] implement the first narrow job/job-spec persistence slice:
          - [x] `backend/db/job_spec_persistence.py`
          - [x] `backend/services/job_spec_persistence.py`
          - [x] `scripts/persist_tw398_job_spec.py`
        - [x] run the first live `tw398` persistence proof and verify the
          canonical rows/links landed in Supabase
      - [ ] Formalise the advert-response ingestion rule in docs:
        - [ ] JobAdder application = vacancy/application context
        - [ ] JobAdder candidate attachment = structured CV source of truth
        - [ ] Dropbox `.eml` = provenance/history layer
        - [ ] Dropbox CV file copies = archive/mirror layer unless a later
          hash comparison disproves that assumption
      - [x] Implement the first narrow JobAdder application persistence slice:
        - [x] add JobAdder application-detail helper/route
        - [x] persist one real `tw398` application into canonical
          `applications`
        - [x] persist/refresh the linked canonical person/candidate rows from
          the JobAdder candidate snapshot when needed
        - [x] verify the canonical application row links to the already
          persisted canonical `tw398` job
        - [x] verify provenance-bearing source records and links landed in
          Supabase
      - [ ] Next follow-up after the first application persistence proof:
        - [ ] persist one Dropbox `.eml` provenance record and link it to the
          relevant job/application/candidate where the identity is clean enough
        - [ ] decide the next Outlook follow-up after the first fully linked
          `tw394` persistence proof:
          - [x] run the first conservative candidate/job reconciliation check
            for the persisted Outlook `tw394` resume
          - [x] first result:
            - [x] canonical job link is strong and should be kept
            - [x] no exact candidate-attachment hash match was found across the
              current `28` JobAdder applications for job `891841`
            - [x] the first Outlook advert-response sample remains
              candidate-unresolved for now
          - [ ] candidate/person auto-linking only when identity is stronger
            than vacancy code + subject/file naming alone
          - [ ] or the next bounded folder in the same persistence pattern
        - [ ] chunk/embed the persisted `tw398` job-spec document so matching
          can use stored spec text instead of ad hoc parsing

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
- [x] Define initial backup and recovery expectations in
  `docs/database_export_restore.md` and enforce them in the controlled runner.

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
- [x] Define embedding model/provider for Phase 1.
- [x] Define embedding dimensions and storage format.
- [x] Define pgvector index approach for the first dataset size.
- [x] Define whether Phase 1 needs vector-only search or hybrid retrieval.
  - [x] Decision: use hybrid retrieval, not vector-only retrieval.
  - [x] Reason: recruiter search needs both exact keyword matching and semantic recall.
- [ ] Define how chunks link back to:
  - [ ] Source document.
  - [ ] Canonical entity.
  - [ ] Source record.
  - [ ] Import run.
- [ ] Add the first practical hybrid retrieval implementation slice:
  - [x] enable `pgvector` in Supabase environments
  - [x] define raw resume chunking policy for existing canonical CV text
  - [x] define job-spec chunking policy
  - [x] decide that structured candidate semantic blocks should be the primary semantic retrieval unit
  - [x] add a dedicated `candidate_semantic_blocks` table for candidate-level semantic retrieval
  - [x] define the first structured block set from canonical data:
    - [x] profile block
    - [x] skills block
    - [x] experience/summary block
  - [x] choose first embedding runtime:
    - [x] OpenAI `text-embedding-3-large`
    - [x] shortened to `1536` dimensions to match the existing pgvector column
  - [x] backfill structured candidate semantic blocks from canonical stored fields
  - [x] embed those structured blocks without source reingestion
  - [x] keep raw `document_chunks` embeddings as secondary evidence rather than the main recruiter-facing retrieval surface
  - [x] merge full-text and vector retrieval with reciprocal rank fusion or equivalent
  - [x] keep LLM reranking as the final shortlist stage
  - [ ] benchmark hybrid retrieval against current FTS-only retrieval on real role briefs
  - [x] run a first tiny live semantic sample before broad rollout:
    - [x] chunk one real resume document
    - [x] generate embeddings for those chunks
    - [x] run one vector-search query against the sample
  - [x] run the first tiny live structured semantic-block sample before broad rollout:
    - [x] build blocks for a small handful of real candidates
    - [x] generate embeddings for those blocks
    - [x] run one semantic candidate query against the sample

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
- [ ] Define bounded workflow-loop behaviour:
  - [ ] explicit plan, retrieve, verify, and stop states
  - [ ] retry and iteration budgets
  - [ ] deterministic completion and failure conditions
  - [ ] persisted trajectory metadata for debugging and evaluation
- [ ] Introduce multiple specialised agents only where separate tool access,
  data ownership, or approval boundaries justify the added complexity.
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
  - [x] Job-to-candidate matching.
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
- [x] Current narrow workflow direction agreed:
  - [x] first-pass retrieval over canonical current resumes
  - [x] shortlist output through `/match`
  - [x] next upgrade path = hybrid retrieval plus reranking, before wider graph expansion
- [x] Canonical current resumes are now downloadable through the backend/UI route.
- [x] Outlook CV archive is ingested into the canonical Dropbox-backed resume path.
- [x] Resume chunks and embeddings are backfilled across the current searchable corpus.
- [x] Add structured candidate semantic blocks for retrieval beyond raw resume text.
- [x] Add the first company-to-candidate discovery slice.
- [x] Add the first "who works there / who has spoken to them before" lookup slice.
- [x] Add the first relationship-context evidence surface for outreach support.

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
- [x] Add a first internal review surface for canonical Supabase data:
  - [x] backend overview route: `/api/v1/review/overview`
  - [x] frontend review page: `/review`
- [ ] Re-prioritise import order around static exports now that Tom is
  cancelling JobAdder and Dropbox live usage:
  - [ ] Recruiterflow official backup first
  - [ ] JobAdder full export/zip next
  - [ ] broad Dropbox archive folders after that

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

- JobAdder and Dropbox live integration work was still useful because it let us
  map the schema, prove `tw...` vacancy linking, and verify file/provenance
  behaviour against real data.
- Tom is now cancelling JobAdder and Dropbox, so the practical next import mode
  should shift toward:
  - Recruiterflow official backup
  - JobAdder full export/zip
  - broad Dropbox archive folders where still useful
- The first internal Supabase review surface is now live:
  - API: `/api/v1/review/overview`
  - UI: `/review`

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
- [ ] Define retrieval quality fixtures:
  - [ ] versioned real role briefs
  - [ ] recruiter-labelled relevant, borderline, and unsuitable candidates
  - [ ] known strong candidates that retrieval must not miss
- [ ] Define retrieval measures:
  - [ ] recall at the candidate-pool cutoff
  - [ ] reciprocal rank
  - [ ] ranking quality such as nDCG
- [ ] Define matching quality fixtures and measures:
  - [ ] precision and ordering of the final shortlist
  - [ ] strengths, gaps, and evidence coverage
  - [ ] false-positive and missed-candidate review
- [ ] Define groundedness checks.
- [ ] Define hallucination checks.
- [ ] Define action-safety checks.
- [ ] Define authentication, sensitive-data exposure, and future write-action
  safety checks.
- [ ] Define a rubric-based LLM-as-judge check as secondary evidence only.
- [ ] Define human recruiter review and disagreement handling as the primary
  business-quality evaluation.
- [ ] Define multi-turn conversation and LangGraph trajectory evaluations once
  those workflows are active.
- [ ] Explicitly exclude BLEU and ROUGE as primary candidate-matching metrics;
  they measure text overlap rather than recruiter relevance.
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
- The first bounded Recruiterflow static import slice is now live:
  - `job/1.134.json` persisted `134` jobs
  - `candidate/1.100.json` persisted `100` candidates
  - `169` recruiterflow candidate-job applications were resolved
  - the next import step should widen entity coverage carefully rather than
    reinventing the first canonical write path.
- The first bounded Recruiterflow attachment-reference slice is now live:
  - `candidate/files` from `candidate/1.100.json` persisted `106` canonical
    document references
  - `job/files` from `job/1.134.json` persisted `7` canonical document
    references
  - file bytes are still deferred; this slice exists to surface the document
    layer and provenance cleanly before bulk byte ingestion
- The first bounded Recruiterflow candidate-file content slice is now live:
  - `15` primary candidate attachments from `candidate/1.100.json` were
    downloaded and extracted successfully
  - the importer now reads embedded export members under:
    - `candidate/files/{candidate_id}/...`
  - the signed JSON file URLs proved stale/expired and should be treated as
    provenance/fallback metadata, not as the primary byte source for the
    official backup
- The first full Recruiterflow candidate-file content chunk is now live:
  - all `106` candidate attachments from `candidate/1.100.json` were
    downloaded and extracted successfully
  - live review health now shows:
    - `candidate_attachment.total = 106`
    - `reference_only = 0`
    - `byte_backed = 106`
    - `extracted_successfully = 106`
- The next Recruiterflow candidate chunk is now live end to end:
  - `candidate/101.200.json`
  - `100` candidates persisted
  - `101` candidate file references persisted
  - `101` candidate file-content rows persisted
  - `100` extracted successfully
  - `1` unsupported legacy `.doc`
  - `0` failed

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
