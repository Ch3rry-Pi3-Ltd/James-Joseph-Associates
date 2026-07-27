# Linked Helper Person Ingest

This is the first operator path for getting Linked Helper data into the canonical backend.

## Protected route

`POST /api/v1/integrations/linkedin-helper/admin/ingest-person`

The route:

- preserves the raw upstream payload in `source_records`
- upserts canonical `people`
- upserts canonical `companies`
- supports neutral person rows for generic integrations
- upserts canonical `contacts` for `contact` / `hiring_manager`
- upserts canonical `candidates` for `candidate`
- upserts `person_company_roles`
- writes provenance links into `source_record_links`

## Supported record kinds

- `person`
- `candidate`
- `contact`
- `hiring_manager`

Native Linked Helper backup profiles are treated as candidates by operator
decision. Deterministic reconciliation updates the candidate already attached
to the matched person; otherwise it creates a candidate for the new person.
Ambiguous identities remain skipped rather than creating duplicates. Generic
webhook and CSV integrations may still use `person` where their source context
is genuinely unknown.

For an existing candidate, Linked Helper fills missing candidate context and
adds person/company/role/skill provenance. It does not replace an already
populated current title, current company, status, or availability with an older
backup value. Timestamp fields only move forward.

## Operator script

Use:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_linkedin_helper_person_ingest.py `
  --payload-file .\docs\linked-helper-person.sample.json
```

The script loads the admin bearer token from `.env.local` using:

- `ADMIN_API_TOKEN`
- `INTERNAL_ADMIN_API_TOKEN`
- fallback `MAKE_API_TOKEN`

## Sample payload fields

The backend accepts a normalized JSON payload such as:

- `source_record_id`
- `source_payload`
- `record_kind`
- `full_name`
- `first_name`
- `last_name`
- `primary_email`
- `primary_phone`
- `linkedin_url`
- `location`
- `headline`
- `summary`
- `company_name`
- `company_domain`
- `company_website_url`
- `company_linkedin_url`
- `role_title`
- `seniority`
- `postcode`
- `contact_type`
- `is_hiring_manager`
- `is_current_company`
- `role_start_date`
- `role_end_date`
- `candidate_status`
- `availability_status`
- `resume_updated_at`
- `last_contacted_at`

## Native backup dry run

The `.lhd2` backup path is intentionally read-only:

```powershell
.\.venv\Scripts\python.exe -m scripts.dry_run_linkedin_helper_backup `
  --dry-run `
  --entity people `
  --limit 100
```

This downloads the latest backup to memory, maps a bounded profile slice, and
reports aggregate reconciliation counts. It does not extract the SQLite
database to disk and does not write canonical data.

Use `--entity companies` for the equivalent organisation report, or
`--entity both` to report both entities. Name-based matching is only
deterministic when the normalised identity is unique across the complete
backup, regardless of the selected offset and limit.

## Controlled native backup import

Preview a bounded 20-profile plan without writes:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_linkedin_helper_backup_import `
  --limit 20
```

After reviewing the aggregate plan, execute that same bounded slice:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_linkedin_helper_backup_import `
  --limit 20 `
  --commit
```

The command skips ambiguous identities, persists only deterministic matched or
new profiles, resolves linked organisations against the complete backup,
retains connection metadata in provenance, and writes canonical employment
roles plus person- and candidate-level skills. It finishes with a provenance-link audit and
fails if any expected source row lacks exactly one canonical entity link.

Candidate semantic backfill also accepts candidate profiles without a linked
CV, so Linked Helper-only candidates can receive profile/focus/skill embeddings.
When a CV is linked later, rebuilding that candidate adds resume-derived
semantic blocks without reingesting the Linked Helper source.

Apply migration `0010_person_skills.sql` before the first committed run.

### Production proof

The first committed production slice was run on 27 July 2026 with
`--offset 880 --limit 20`. It persisted:

- 20 canonical people/candidates
- 114 deterministically reconciled companies
- 171 employment-role links
- 767 person/candidate skill links

Four ambiguous company identities were deliberately excluded. The post-write
audit found exactly one canonical provenance link for all 20 expected people
and all 114 expected companies. A read-only rerun classified all 20 people and
all 114 safe companies as existing matches, confirming idempotent source-link
recognition.

Webhook/CSV paths can continue to use the same normalized persistence shape:

- a webhook adapter route
- or a batch CSV-to-JSON import path
