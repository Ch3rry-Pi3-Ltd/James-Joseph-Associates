-- Neutral Linked Helper profiles are canonical people until another source
-- establishes that they are candidates or contacts. Keep their skills linked
-- to people rather than inventing a candidate classification.
create table if not exists person_skills (
    id uuid primary key default gen_random_uuid(),
    person_id uuid not null references people(id) on delete cascade,
    skill_id uuid not null references skills(id) on delete cascade,
    source_record_id uuid references source_records(id) on delete set null,
    created_at timestamptz not null default now(),
    constraint person_skills_person_skill_unique unique (person_id, skill_id)
);

create index if not exists idx_person_skills_person_id
    on person_skills (person_id);

create index if not exists idx_person_skills_skill_id
    on person_skills (skill_id);
