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

## Restartable backup batches

Use the batch runner for the complete native backup. It downloads and maps the
backup in memory, writes one bounded batch per transaction, audits every
expected provenance link, and advances an ignored local checkpoint only after
the audit passes.

Start a new run:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_linkedin_helper_backup_batches `
  --batch-size 20 `
  --max-batches 5 `
  --reset-checkpoint `
  --commit
```

Resume from the last audited offset:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_linkedin_helper_backup_batches `
  --resume `
  --batch-size 20 `
  --max-batches 5 `
  --commit
```

Omit `--commit` to preview the next batches without database writes or
checkpoint changes. The runner validates the Dropbox path, backup hash, and
profile count before resuming. Its default `2.5 GiB` database-size ceiling
stops new batches before the current Supabase database grows beyond the
conservative operating limit; change that ceiling only after reviewing the
active Supabase plan.

The default related-company limit is `250` per transaction. For a reviewed
larger batch, `--max-related-companies 500` can raise that memory and write
boundary explicitly; the plan is rejected before writes if the selected slice
exceeds it.

The checkpoint contains offsets and aggregate counts only. It is stored at
`temp/linkedin_helper_backup_import_checkpoint.json` and excluded from Git.
If a database transaction or audit fails, the checkpoint does not advance, so
the same batch can be rerun safely.

### Batch-run proof

Restartable production batches completed the full native backup through source
offset `10,862` on
28 July 2026. The checkpoint records:

- 10,273 deterministic people/candidates persisted
- 34,838 reconciled companies persisted
- 54,746 employment roles persisted
- 46,141 skill links persisted
- exact people and company provenance audits passing after every batch

The 3,000-profile run from offset `1,400` to `4,400` persisted 2,875
deterministic people and safely excluded 125 ambiguous identities. It grew the
database by approximately 23.1 MiB, from 2.262 GiB to 2.285 GiB, remaining
below the configured 2.5 GiB ceiling.

The next 3,000-profile run from offset `4,400` to `7,400` persisted 2,823
deterministic people and safely excluded 177 ambiguous identities. It also
persisted 9,313 reconciled companies, 15,100 employment roles, and 6,063 skill
links. All 30 batch audits passed. The database grew by approximately 22.9 MiB
to 2.307 GiB, remaining below the configured ceiling.

The final 3,462-profile run from offset `7,400` to `10,862` persisted 3,237
deterministic people and safely excluded 225 ambiguous identities. It also
persisted 10,269 reconciled companies, 16,351 employment roles, and 2,732 skill
links. All 35 batch audits passed. The database grew by approximately 18.7 MiB
to 2.325 GiB, remaining below the configured ceiling.

The full backup contained 10,862 source profiles. The audited checkpoint is at
the final offset with zero profiles remaining.

Webhook/CSV paths can continue to use the same normalized persistence shape:

- a webhook adapter route
- or a batch CSV-to-JSON import path
