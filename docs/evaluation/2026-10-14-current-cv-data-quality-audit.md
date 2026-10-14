# Current-CV data-quality audit — 14 October 2026

## Outcome

The canonical current-CV collection is technically sound for search:

- all `16,102` current CV documents have extracted text
- all `16,102` have an indexed full-text search vector
- all `16,102` candidates have semantic blocks and embeddings
- all `16,102` documents have source-record provenance
- every candidate with a current CV has exactly one selected document
- there are no duplicate current-link rows, non-resume current links, missing
  person mirrors, or current documents missing from resume history

The audit therefore found no broken canonical-link or search-index invariant.
It did find material completeness, freshness, downloadability, and structured
evidence gaps that should remain visible rather than being inferred away.

## Method

`scripts/audit_current_resume_data_quality.py` ran against live Supabase in a
database-enforced read-only transaction. It returned aggregate counts only:
no candidate identifiers, names, contact details, source URLs, or CV text were
printed or written to the repository. The audit performed zero writes.

The checks covered:

- current-link uniqueness and candidate/person mirroring
- extracted-text and indexed-search readiness
- source provenance and download-locator recoverability
- structured title, company, skills, and employment evidence
- CV freshness
- semantic retrieval readiness
- duplicate content-hash and source-URI signals

## Corpus and search coverage

| Measure | Result |
| --- | ---: |
| Canonical candidates | 25,820 |
| Candidates/current documents with a selected CV | 16,102 |
| Candidates without resume history | 9,718 |
| Candidate current-CV coverage | 62.36% |
| Current CVs with extracted text | 100% |
| Current CVs with a search vector | 100% |
| Current-CV candidates with semantic embeddings | 100% |
| Current documents with provenance | 100% |

“Exhaustive current-CV search” is accurate for all `16,102` documents in its
declared scope. It is not a claim that all `25,820` candidates have a CV: the
`9,718` candidates without resume history are outside that document-search
scope and remain available only through other profile evidence.

The previously reported `32,204` eligible-document figure was a coverage-count
defect. It counted both the candidate current-CV link and its mirrored person
link. The search results themselves were not duplicated because result rows
join through a non-null candidate ID. The database query has now been corrected
to count/search candidate-linked documents only, with a PostgreSQL regression
test that includes both link types. Running the corrected local code against the
live database returned `16,102` eligible and searchable documents, zero
missing-text exclusions, and `9,718` candidates without a current resume.

## Evidence completeness and freshness

| Measure | Covered | Missing |
| --- | ---: | ---: |
| Structured current title | 84.93% | 2,426 |
| Structured current company | 85.73% | 2,298 |
| Structured skills | 97.81% | 353 |
| Structured employment history | 3.20% | 15,586 |
| Resume updated within two years | 65.75% | 5,515 older than two years |

No effective resume date is missing or more than one day in the future. The
`5,515` older documents are between two and five years old; none is older than
five years according to the stored effective date.

The largest evidence gap is structured employment history. Full CV text and
semantic evidence still exist, but deterministic timeline-style employment
comparisons cannot rely on `person_company_roles` for most candidates. Current
title and company coverage are substantially better, though still incomplete.

## Text and file quality

| Measure | Result |
| --- | ---: |
| Median extracted text | 7,506 characters |
| 5th percentile | 2,593 characters |
| 95th percentile | 18,000 characters |
| Very short extractions (under 200 characters) | 5 |
| Missing MIME type | 902 |
| Missing content hash | 0 |
| Duplicate content-hash groups across candidates | 0 |
| Duplicate source-URI groups | 13 groups / 26 candidates |

The five very short extractions need a bounded private review. The thirteen
shared source-URI groups are review signals, not proof of duplicate candidates;
no record should be merged or deleted without inspecting provenance.

## Downloadability

`2,937` documents have no direct `source_uri` or storage path. This is not the
true failure count:

- `2,646` Dropbox locators can be reconstructed from existing provenance by the
  application
- `291` Recruiterflow-backed CVs have no direct or provenance-derivable locator
- effective current-CV download-locator coverage is therefore `98.19%`

Those `291` CVs remain searchable because their extracted text is present, but
the original file cannot currently be retrieved through the application.

Document provenance includes Dropbox (`15,794` documents), Recruiterflow
(`3,402`), Outlook (`6`), and JobAdder (`2`). These source counts overlap where
one canonical document is backed by more than one source system.

## Retrieval-storage note

`12,843` current documents have no legacy `document_chunks`/chunk embeddings.
This is not a current retrieval failure: all `16,102` current-CV candidates have
the newer candidate semantic blocks and embeddings used by hybrid search.
Backfilling the older chunk store solely to improve this metric is not justified.

## Independent follow-up priorities

1. Deploy and production-smoke the corrected `16,102`-document coverage count.
2. Privately inspect the five very short extractions and decide whether their
   source files should be re-extracted.
3. Review the thirteen shared source-URI groups without destructive merging.
4. Represent the `291` Recruiterflow documents as searchable but not currently
   downloadable; recover source references only if a trustworthy source exists.
5. Backfill structured employment history, followed by missing current title,
   company, and skills, from already persisted evidence with provenance and
   deterministic verification.

Recruiter-labelled relevance is not needed for these engineering steps. Tom is
still needed later to decide whether the resulting freshness and evidence mix
is useful enough for his live recruitment workflow.
