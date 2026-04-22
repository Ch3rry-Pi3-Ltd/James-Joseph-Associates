-- Prototype seed data for the provisional Supabase schema.
--
-- This seed is intentionally tiny.
-- Its job is to prove:
--
-- - tables can accept inserts
-- - foreign-key relationships work
-- - simple joins and lookups work
-- - source records can link back to canonical entities
-- - document and chunk retrieval shape is usable
--
-- This is not representative production data.

BEGIN;

-- ============================================================================
-- Companies
-- ============================================================================

INSERT INTO companies (
    id,
    name,
    domain,
    website_url,
    linkedin_url,
    industry,
    size_range,
    location,
    description,
    status
)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'Acme Hiring Ltd',
    'acmehiring.example',
    'https://acmehiring.example',
    'https://linkedin.com/company/acme-hiring',
    'Recruitment',
    '11-50',
    'London, UK',
    'Prototype client company for schema testing.',
    'active'
);

-- ============================================================================
-- People
-- ============================================================================

INSERT INTO people (
    id,
    full_name,
    first_name,
    last_name,
    primary_email,
    primary_phone,
    linkedin_url,
    location,
    headline,
    summary
)
VALUES
(
    '22222222-2222-2222-2222-222222222221',
    'Sarah Jones',
    'Sarah',
    'Jones',
    'sarah.jones@example.com',
    '+447700900111',
    'https://linkedin.com/in/sarah-jones',
    'London, UK',
    'Senior Data Engineer',
    'Prototype candidate person record.'
),
(
    '22222222-2222-2222-2222-222222222222',
    'Tom Richards',
    'Tom',
    'Richards',
    'tom.richards@acmehiring.example',
    '+447700900222',
    'https://linkedin.com/in/tom-richards',
    'Manchester, UK',
    'Head of Talent',
    'Prototype contact person record.'
);

-- ============================================================================
-- Candidates
-- ============================================================================

INSERT INTO candidates (
    id,
    person_id,
    current_title,
    current_company_id,
    candidate_status,
    availability_status,
    salary_expectation,
    notice_period,
    last_contacted_at,
    resume_updated_at
)
VALUES (
    '33333333-3333-3333-3333-333333333331',
    '22222222-2222-2222-2222-222222222221',
    'Senior Data Engineer',
    '11111111-1111-1111-1111-111111111111',
    'active',
    'open_to_move',
    95000.00,
    '1 month',
    NOW() - INTERVAL '7 days',
    NOW() - INTERVAL '2 days'
);

-- ============================================================================
-- Contacts
-- ============================================================================

INSERT INTO contacts (
    id,
    person_id,
    company_id,
    role_title,
    contact_type,
    seniority,
    is_hiring_manager,
    postcode
)
VALUES (
    '44444444-4444-4444-4444-444444444441',
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'Head of Talent',
    'client_contact',
    'head',
    true,
    'M1 1AA'
);

-- ============================================================================
-- Jobs
-- ============================================================================

INSERT INTO jobs (
    id,
    company_id,
    hiring_manager_contact_id,
    title,
    description,
    location,
    workplace_type,
    employment_type,
    work_type,
    source,
    owner_name,
    salary_min,
    salary_max,
    currency,
    status,
    opened_at,
    updated_from_source_at
)
VALUES (
    '55555555-5555-5555-5555-555555555551',
    '11111111-1111-1111-1111-111111111111',
    '44444444-4444-4444-4444-444444444441',
    'Senior Data Engineer',
    'Build data pipelines and support analytics workflows.',
    'Manchester, UK',
    'hybrid',
    'permanent',
    'full_time',
    'jobadder',
    'Roger',
    85000.00,
    100000.00,
    'GBP',
    'open',
    NOW() - INTERVAL '14 days',
    NOW() - INTERVAL '1 day'
);

-- ============================================================================
-- Applications
-- ============================================================================

INSERT INTO applications (
    id,
    candidate_id,
    job_id,
    application_status,
    source,
    rating,
    candidate_rating,
    current_position,
    current_employer,
    social_profiles,
    applied_at
)
VALUES (
    '66666666-6666-6666-6666-666666666661',
    '33333333-3333-3333-3333-333333333331',
    '55555555-5555-5555-5555-555555555551',
    'interview',
    'jobadder',
    'strong',
    '4/5',
    'Senior Data Engineer',
    'Acme Hiring Ltd',
    '{"linkedin":"https://linkedin.com/in/sarah-jones"}'::jsonb,
    NOW() - INTERVAL '5 days'
);

-- ============================================================================
-- Placements
-- ============================================================================

INSERT INTO placements (
    id,
    candidate_id,
    job_id,
    company_id,
    contact_id,
    placement_status,
    start_date,
    end_date
)
VALUES (
    '77777777-7777-7777-7777-777777777771',
    '33333333-3333-3333-3333-333333333331',
    '55555555-5555-5555-5555-555555555551',
    '11111111-1111-1111-1111-111111111111',
    '44444444-4444-4444-4444-444444444441',
    'proposed',
    CURRENT_DATE + 30,
    NULL
);

-- ============================================================================
-- Opportunities
-- ============================================================================

INSERT INTO opportunities (
    id,
    title,
    smart_summary,
    company_id,
    contact_id,
    stage,
    last_contact_at,
    next_task_at,
    value
)
VALUES (
    '88888888-8888-8888-8888-888888888881',
    'Data team expansion',
    'Prototype business-development opportunity.',
    '11111111-1111-1111-1111-111111111111',
    '44444444-4444-4444-4444-444444444441',
    'qualified',
    NOW() - INTERVAL '3 days',
    NOW() + INTERVAL '2 days',
    25000.00
);

-- ============================================================================
-- Skills
-- ============================================================================

INSERT INTO skills (
    id,
    name,
    canonical_name,
    skill_type,
    description
)
VALUES
(
    '99999999-9999-9999-9999-999999999991',
    'Python',
    'python',
    'technical',
    'Programming language skill.'
),
(
    '99999999-9999-9999-9999-999999999992',
    'SQL',
    'sql',
    'technical',
    'Query and relational database skill.'
);

-- ============================================================================
-- Documents
-- ============================================================================

INSERT INTO documents (
    id,
    document_type,
    title,
    source_uri,
    storage_path,
    mime_type,
    content_hash,
    extracted_text
)
VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
    'cv',
    'Sarah Jones CV',
    'dropbox://cv/sarah-jones.pdf',
    'prototype/cvs/sarah-jones.pdf',
    'application/pdf',
    'prototype-hash-sarah-jones-cv',
    'Sarah Jones is a Senior Data Engineer with strong Python and SQL skills.'
);

-- ============================================================================
-- Interactions
-- ============================================================================

INSERT INTO interactions (
    id,
    interaction_type,
    occurred_at,
    subject,
    body,
    summary,
    source_system
)
VALUES (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1',
    'email',
    NOW() - INTERVAL '4 days',
    'Initial candidate outreach',
    'Reached out to candidate regarding Senior Data Engineer role.',
    'Prototype outreach interaction.',
    'jobadder'
);

-- ============================================================================
-- Source records
-- ============================================================================

INSERT INTO source_records (
    id,
    source_system,
    source_record_type,
    source_record_id,
    source_payload,
    source_payload_hash,
    import_run_id,
    received_at,
    processed_at,
    sync_status,
    error_message
)
VALUES
(
    'cccccccc-cccc-cccc-cccc-ccccccccccc1',
    'jobadder',
    'candidate',
    'candidate-123',
    '{"name":"Sarah Jones","email":"sarah.jones@example.com","status":"active"}'::jsonb,
    'hash-jobadder-candidate-123',
    'prototype-run-001',
    NOW() - INTERVAL '10 minutes',
    NOW() - INTERVAL '9 minutes',
    'processed',
    NULL
),
(
    'cccccccc-cccc-cccc-cccc-ccccccccccc2',
    'dropbox',
    'document',
    'dropbox-cv-001',
    '{"file_name":"sarah-jones.pdf","path":"prototype/cvs/sarah-jones.pdf"}'::jsonb,
    'hash-dropbox-cv-001',
    'prototype-run-001',
    NOW() - INTERVAL '10 minutes',
    NOW() - INTERVAL '8 minutes',
    'processed',
    NULL
);

-- ============================================================================
-- Relationship tables
-- ============================================================================

INSERT INTO candidate_skills (
    id,
    candidate_id,
    skill_id,
    source_record_id,
    confidence,
    evidence_text
)
VALUES
(
    'dddddddd-dddd-dddd-dddd-ddddddddddd1',
    '33333333-3333-3333-3333-333333333331',
    '99999999-9999-9999-9999-999999999991',
    'cccccccc-cccc-cccc-cccc-ccccccccccc1',
    0.9800,
    'Python mentioned in CV and job history.'
),
(
    'dddddddd-dddd-dddd-dddd-ddddddddddd2',
    '33333333-3333-3333-3333-333333333331',
    '99999999-9999-9999-9999-999999999992',
    'cccccccc-cccc-cccc-cccc-ccccccccccc1',
    0.9700,
    'SQL mentioned in CV and project experience.'
);

INSERT INTO job_required_skills (
    id,
    job_id,
    skill_id,
    requirement_type,
    importance,
    source_record_id
)
VALUES
(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1',
    '55555555-5555-5555-5555-555555555551',
    '99999999-9999-9999-9999-999999999991',
    'required',
    'high',
    'cccccccc-cccc-cccc-cccc-ccccccccccc1'
),
(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee2',
    '55555555-5555-5555-5555-555555555551',
    '99999999-9999-9999-9999-999999999992',
    'required',
    'high',
    'cccccccc-cccc-cccc-cccc-ccccccccccc1'
);

INSERT INTO person_company_roles (
    id,
    person_id,
    company_id,
    role_title,
    start_date,
    end_date,
    is_current,
    source_record_id
)
VALUES
(
    'ffffffff-ffff-ffff-ffff-fffffffffff1',
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'Head of Talent',
    CURRENT_DATE - 365,
    NULL,
    true,
    'cccccccc-cccc-cccc-cccc-ccccccccccc1'
);

INSERT INTO document_links (
    id,
    document_id,
    candidate_id,
    source_record_id,
    relationship_type
)
VALUES (
    '12121212-1212-1212-1212-121212121212',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
    '33333333-3333-3333-3333-333333333331',
    'cccccccc-cccc-cccc-cccc-ccccccccccc2',
    'candidate_cv'
);

INSERT INTO interaction_participants (
    id,
    interaction_id,
    candidate_id,
    contact_id,
    job_id,
    role_in_interaction
)
VALUES
(
    '13131313-1313-1313-1313-131313131313',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1',
    '33333333-3333-3333-3333-333333333331',
    NULL,
    '55555555-5555-5555-5555-555555555551',
    'candidate'
),
(
    '14141414-1414-1414-1414-141414141414',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1',
    NULL,
    '44444444-4444-4444-4444-444444444441',
    '55555555-5555-5555-5555-555555555551',
    'client_contact'
);

INSERT INTO source_record_links (
    id,
    source_record_id,
    candidate_id,
    document_id
)
VALUES
(
    '15151515-1515-1515-1515-151515151515',
    'cccccccc-cccc-cccc-cccc-ccccccccccc1',
    '33333333-3333-3333-3333-333333333331',
    NULL
),
(
    '16161616-1616-1616-1616-161616161616',
    'cccccccc-cccc-cccc-cccc-ccccccccccc2',
    NULL,
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1'
);

-- ============================================================================
-- Document chunks
-- ============================================================================

INSERT INTO document_chunks (
    id,
    document_id,
    source_record_id,
    chunk_index,
    chunk_text,
    embedding,
    token_count
)
VALUES
(
    '17171717-1717-1717-1717-171717171717',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
    'cccccccc-cccc-cccc-cccc-ccccccccccc2',
    0,
    'Sarah Jones is a Senior Data Engineer with strong Python experience.',
    NULL,
    12
),
(
    '18181818-1818-1818-1818-181818181818',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
    'cccccccc-cccc-cccc-cccc-ccccccccccc2',
    1,
    'She has strong SQL skills and experience building data pipelines.',
    NULL,
    11
);

COMMIT;
