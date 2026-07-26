---
title: "Current Supabase Data Model and Extracted Information"
subtitle: "Recruitment Intelligence Platform"
author: "James Joseph Associates"
date: "20 July 2026"
toc: true
toc-depth: 2
numbersections: true
colorlinks: true
linkcolor: teal
urlcolor: teal
documentclass: article
fontsize: 11pt
geometry:
  - margin=1in
header-includes:
  - |
    \usepackage{titlesec}
    \usepackage{enumitem}
    \usepackage{xcolor}
    \usepackage{helvet}
    \renewcommand{\familydefault}{\sfdefault}
    \definecolor{brandgreen}{HTML}{0F7B6C}
    \definecolor{brandink}{HTML}{15232D}
    \definecolor{brandmuted}{HTML}{566370}
    \titleformat{\section}{\Large\bfseries\color{brandink}}{\thesection}{0.75em}{}
    \titleformat{\subsection}{\large\bfseries\color{brandgreen}}{\thesubsection}{0.75em}{}
    \titleformat{\subsubsection}{\normalsize\bfseries\color{brandink}}{\thesubsubsection}{0.75em}{}
    \setlist[itemize]{leftmargin=1.5em,itemsep=0.35em,topsep=0.35em}
    \setlist[enumerate]{leftmargin=1.5em,itemsep=0.35em,topsep=0.35em}
    \setcounter{secnumdepth}{2}
---

# Overview

This document summarises the current implemented structure of the Supabase database behind the recruitment intelligence platform.

The model is designed around four layers:

1. **Canonical records** such as candidates, companies, contacts, jobs, opportunities, documents, and interactions.
2. **Relationship records** that link those entities together.
3. **Provenance records** that preserve where each row came from originally.
4. **Retrieval records** such as chunks and embeddings used for semantic and GraphRAG-style search.

The key point is that the schema is broader than any single ingestion path. Some source pipelines populate only part of the model, but the overall structure is already in place.

# Candidate and CV Data

## `people`

This is the person-level identity record.

**Fields**

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

## `candidates`

This is the candidate-specific record linked to a person.

**Fields**

- `id`
- `person_id`
- `current_title`
- `current_company_id`
- `candidate_status`
- `availability_status`
- `salary_expectation`
- `notice_period`
- `last_contacted_at`
- `resume_updated_at`
- `created_at`
- `updated_at`

## Structured Information Extracted from CVs

The CV extraction layer currently pulls out structured information such as:

- full name
- first name
- last name
- current employer
- current title
- professional summary
- location
- email addresses
- phone numbers
- LinkedIn URL
- core skills
- tools and platforms
- certifications
- portfolio references
- education history
- employment history
- project experience
- evidence notes
- ambiguity notes

## What Is Currently Persisted from CVs

From CV ingestion, the current write paths persist:

- person identity and contact fields
- candidate role and status fields
- current company link where available
- resume updated date
- extracted skills
- full extracted resume text
- provenance back to the original file and source

# Company Data

## `companies`

This is the canonical company record.

**Fields**

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

## Current Population Status

Depending on source, we currently populate some or all of:

- company name
- website and domain
- LinkedIn URL
- industry or sector
- location
- description
- status

For CV-only ingestion, company population is still narrower. For Recruitly and LinkedIn Helper style sources, company records are richer.

# Company Contacts and Hiring Managers

## `contacts`

This is the canonical client contact or hiring manager record.

**Fields**

- `id`
- `person_id`
- `company_id`
- `role_title`
- `contact_type`
- `seniority`
- `is_hiring_manager`
- `postcode`
- `created_at`
- `updated_at`

## What Can Be Stored for Contacts

We can currently hold:

- name
- email
- phone
- LinkedIn URL
- location
- role title
- seniority
- hiring-manager flag
- linked company
- postcode
- source provenance

# Jobs and Vacancies

## `jobs`

This is the canonical job or vacancy record.

**Fields**

- `id`
- `company_id`
- `hiring_manager_contact_id`
- `title`
- `description`
- `location`
- `workplace_type`
- `employment_type`
- `work_type`
- `source`
- `owner_name`
- `salary_min`
- `salary_max`
- `currency`
- `status`
- `opened_at`
- `closed_at`
- `updated_from_source_at`
- `created_at`
- `updated_at`

This supports the “find candidates for a role” workflows.

# Opportunities and Commercial Pipeline

## `opportunities`

This is the canonical opportunity or client-opportunity record.

**Fields**

- `id`
- `title`
- `smart_summary`
- `company_id`
- `contact_id`
- `stage`
- `last_contact_at`
- `next_task_at`
- `value`
- `created_at`
- `updated_at`

This supports workflows around target companies, prior commercial context, and hiring activity.

# Skills

## `skills`

This is the normalised master list of skills.

**Fields**

- `id`
- `name`
- `canonical_name`
- `skill_type`
- `description`
- `created_at`
- `updated_at`

## `candidate_skills`

This links candidates to skills.

**Fields**

- `id`
- `candidate_id`
- `skill_id`
- `source_record_id`
- `confidence`
- `evidence_text`
- `created_at`

## `job_required_skills`

This links jobs to required or preferred skills.

**Fields**

- `id`
- `job_id`
- `skill_id`
- `requirement_type`
- `importance`
- `source_record_id`
- `created_at`

# Documents and CV Files

## `documents`

This stores the document-level record, including CVs.

**Fields**

- `id`
- `document_type`
- `title`
- `source_uri`
- `storage_path`
- `mime_type`
- `content_hash`
- `extracted_text`
- `resume_updated_at`
- `created_at`
- `updated_at`

For CVs this means we keep:

- the file identity
- the source path or URI
- the extracted text
- the content hash
- the document type
- the last updated date where available

# Notes, Calls, Meetings, Emails, and Interaction Evidence

## `interactions`

This stores first-class interaction history.

**Fields**

- `id`
- `interaction_type`
- `occurred_at`
- `subject`
- `body`
- `summary`
- `source_system`
- `created_at`
- `updated_at`

## `interaction_participants`

This links an interaction to the relevant entities.

**Fields**

- `id`
- `interaction_id`
- `person_id`
- `candidate_id`
- `contact_id`
- `company_id`
- `job_id`
- `role_in_interaction`
- `created_at`

This is what allows the system to support questions such as:

- who have we spoken to at this company?
- when did we last speak to them?
- which candidate, contact, company, or job was that interaction tied to?

# Relationship Tables

## `person_company_roles`

This stores who worked where, and when.

**Fields**

- `id`
- `person_id`
- `company_id`
- `role_title`
- `start_date`
- `end_date`
- `is_current`
- `source_record_id`
- `created_at`

## `document_links`

This links a document to one or more entities.

**Fields**

- `id`
- `document_id`
- `person_id`
- `candidate_id`
- `contact_id`
- `company_id`
- `job_id`
- `application_id`
- `placement_id`
- `source_record_id`
- `relationship_type`
- `created_at`

This is how a CV is linked back to the right candidate and person.

# Provenance and Source Tracking

## `source_records`

This stores the original upstream source record.

**Fields**

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
- `created_at`

## `source_record_links`

This links each source record to whichever canonical rows it created or updated.

**Fields**

- `id`
- `source_record_id`
- `person_id`
- `candidate_id`
- `contact_id`
- `company_id`
- `job_id`
- `application_id`
- `placement_id`
- `opportunity_id`
- `document_id`
- `linked_at`

This layer is critical because it gives us:

- deduplication support
- audit trail
- source-system traceability
- safer updates later

# Retrieval and GraphRAG Support

## `document_chunks`

This stores chunked text from documents for retrieval.

**Fields**

- `id`
- `document_id`
- `source_record_id`
- `chunk_index`
- `chunk_text`
- `embedding`
- `token_count`
- `created_at`

## `candidate_semantic_blocks`

This stores structured candidate retrieval blocks.

**Fields**

- `id`
- `candidate_id`
- `person_id`
- `document_id`
- `block_type`
- `block_index`
- `block_label`
- `block_text`
- `embedding`
- `token_count`
- `created_at`
- `updated_at`

These blocks are built from candidate profile facts such as:

- name
- current title
- current company
- location
- headline
- summary
- candidate status
- availability
- notice period
- resume updated date
- linked skills
- resume context excerpt

This is what powers the semantic retrieval layer behind the matching workflow.

# What the System Already Supports

In practical terms, the current platform already stores and links:

- candidates
- their CV files and extracted text
- their skills
- their current role and company
- companies
- company contacts and hiring managers
- jobs
- opportunities
- interaction evidence and notes
- source provenance
- semantic retrieval blocks for matching and GraphRAG-style search

# Practical Caveat

The schema is broader than any one ingestion path.

So the correct description is:

- the **database structure already supports** all of the above
- different source pipelines currently populate different subsets
- CV ingestion is strongest on candidate, document, skill, and provenance data
- Recruitly and LinkedIn-style ingestion is stronger for company, contact, job, and opportunity context
- the platform is designed so those sources can be linked together in one canonical graph

# Summary

The current Supabase design is already set up to support Tom’s core workflows:

- finding candidates for jobs
- finding known people and context around target companies
- linking CV evidence back to candidates
- preserving provenance from external systems
- supporting semantic retrieval and future graph-style reasoning

The important operational distinction is not whether the schema can hold the data. It can. The distinction is which ingestion paths are already writing which parts of that schema today.
