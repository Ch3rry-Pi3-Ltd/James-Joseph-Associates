# ChatGPT Business MCP Workflow

## Purpose

This document defines the first practical path for a ChatGPT-style recruiter
assistant that can query the canonical Supabase data safely.

The key design choice is:

- do **not** connect ChatGPT Business directly to raw Supabase
- expose a **read-only MCP app** in front of Supabase
- let Tom use that app from his ChatGPT Business workspace

That gives us:

- grounded answers
- a controlled tool surface
- permission boundaries
- a path to later add approved write actions without exposing the database
  directly

## What Tom Should Be Able To Ask

The first release should support questions such as:

- Who do we know at this company?
- Which candidates fit this job description?
- Who has spoken to this company before?
- What jobs or opportunities are already linked to this account?
- Summarise the prior notes and interaction history for this company.
- Why was this candidate shortlisted?
- Which candidates have Rust and trading-system experience?
- Which people in the database currently work at this firm?

## Recommended V1 Scope

The first release should be **read-only**.

That means:

- search
- retrieval
- evidence assembly
- answer generation
- no mutation of canonical records yet

This keeps the risk low while giving Tom a real operational assistant.

## MCP Tool Surface

The first MCP app should expose a small, explicit toolset.

### 1. Search candidates from a role brief

Purpose:

- take a free-text job description or role brief
- run the existing retrieval + shortlist logic
- return ranked candidates with strengths, gaps, and evidence

Likely backing routes/services:

- candidate search
- candidate shortlist

### 2. Inspect candidate profile

Purpose:

- fetch a full candidate view
- show title, company, skills, linked context, and current-resume metadata

### 3. Open current CV / resume document

Purpose:

- fetch the current canonical resume document reference
- allow the assistant or UI to cite the underlying CV evidence

### 4. Inspect company context

Purpose:

- find a canonical company
- return linked candidates, contacts, jobs, opportunities, and supporting
  evidence

### 5. Inspect known contacts / hiring-manager context

Purpose:

- list known people linked to a company
- surface whether we already know anyone there
- show relationship context where available

### 6. Inspect prior interactions and notes

Purpose:

- return interaction history already stored in canonical form
- support questions about previous conversations and prior recruiter context

### 7. Inspect linked jobs and opportunities

Purpose:

- show open or historical jobs/opportunities linked to a company or contact

### 8. Explain shortlist evidence

Purpose:

- convert the retrieved evidence into a recruiter-facing explanation:
  - why this candidate
  - what are the gaps
  - what evidence supports the ranking

## Memory Model

There are two different kinds of memory here and they should not be confused.

### A. Chat memory

This is the running conversation inside ChatGPT.

Useful for:

- follow-up questions in the same session
- clarifying what Tom means by "that candidate" or "that company"

### B. Operational memory

This is the real business memory and should live in Supabase.

That includes:

- recruiter notes
- prior interactions
- linked documents
- company context
- previous stored conversation summaries if we decide to persist them

Recommended rule:

- ChatGPT session memory is convenience
- Supabase remains the source of truth

## Authentication Model

Tom should connect this through his ChatGPT Business workspace, but the app
itself still needs to enforce access.

Recommended V1:

- approved-workspace users only
- read-only MCP app
- server-side Supabase access via controlled backend credentials
- tool-level access restrictions enforced in the MCP app

That means ChatGPT Business becomes the interface, but our backend remains the
security boundary.

## Rollout Order

### Phase A: Read-only assistant

- expose the MCP app
- enable candidate/company/contact/job/interaction retrieval
- answer grounded recruiter questions

### Phase B: Saved operational context

- persist approved conversation summaries or recruiter notes if useful
- allow the assistant to reference prior stored context more effectively

### Phase C: Approved write actions

Only after the read-only path is trusted:

- save shortlist
- create recruiter note
- draft outbound action
- propose CRM update

Write actions should remain human-approved.

## Why This Is Better Than Direct Database Access

Direct raw database exposure is the wrong boundary.

The MCP layer gives us:

- a stable contract for ChatGPT
- safer permissions
- cleaner schema abstraction
- room to change the Supabase schema without breaking Tom's assistant workflow
- easier auditing and future approval controls

## Immediate Build Tasks

- [ ] Define the exact MCP tool request/response schemas.
- [ ] Map each MCP tool to existing backend routes/services where possible.
- [ ] Add any missing read routes needed for company/contact/interaction lookup.
- [ ] Add read-only auth and audit logging expectations.
- [ ] Decide whether prior recruiter conversations should be:
  - [ ] session-only
  - [ ] persisted as conversation summaries
  - [ ] persisted as first-class interaction records
- [ ] Produce a first test script with realistic recruiter prompts.

## Priority Note

This workflow is now a top-priority product direction because it aligns with
Tom's repeated request for:

- a ChatGPT-style interface
- grounded access to the canonical database
- memory of prior context
- minimal custom reasoning UI beyond what a strong LLM interface can already do
