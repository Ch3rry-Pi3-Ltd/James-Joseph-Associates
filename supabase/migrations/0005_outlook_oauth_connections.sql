create table if not exists outlook_oauth_connections (
    id uuid primary key default gen_random_uuid(),
    access_token text not null,
    refresh_token text,
    token_type text not null,
    expires_in_seconds integer not null,
    obtained_at timestamptz not null,
    scope text,
    microsoft_user_id text not null unique,
    tenant_id text,
    user_principal_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create trigger set_outlook_oauth_connections_updated_at
before update on outlook_oauth_connections
for each row
execute function set_updated_at();
