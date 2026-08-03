BEGIN;

CREATE TABLE api_rate_limit_windows (
    principal_hash text NOT NULL,
    route_group text NOT NULL,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL DEFAULT 0,
    PRIMARY KEY (principal_hash, route_group, window_started_at),
    CONSTRAINT api_rate_limit_windows_request_count_nonnegative
        CHECK (request_count >= 0)
);

CREATE INDEX idx_api_rate_limit_windows_started_at
    ON api_rate_limit_windows (window_started_at);

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jja_app_readonly') THEN
        CREATE ROLE jja_app_readonly NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jja_app_writer') THEN
        CREATE ROLE jja_app_writer NOLOGIN;
    END IF;
END
$roles$;

GRANT jja_app_readonly TO jja_app_writer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO jja_app_readonly, jja_app_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO jja_app_readonly;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO jja_app_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO jja_app_writer;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO jja_app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT INSERT, UPDATE, DELETE ON TABLES TO jja_app_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO jja_app_writer;

COMMIT;
