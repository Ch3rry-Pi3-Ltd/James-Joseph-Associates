# Linked Helper Person Ingest

This is the first operator path for getting Linked Helper data into the canonical backend.

## Protected route

`POST /api/v1/integrations/linkedin-helper/admin/ingest-person`

The route:

- preserves the raw upstream payload in `source_records`
- upserts canonical `people`
- upserts canonical `companies`
- upserts canonical `contacts` for `contact` / `hiring_manager`
- upserts canonical `candidates` for `candidate`
- upserts `person_company_roles`
- writes provenance links into `source_record_links`

## Supported record kinds

- `candidate`
- `contact`
- `hiring_manager`

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

## Next step

Once we have one real Linked Helper webhook or CSV row, map it into this shape and run it through the operator script first. After that, we can add either:

- a webhook adapter route
- or a batch CSV-to-JSON import path
