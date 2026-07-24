BEGIN;

CREATE TABLE mcp_rate_limit_windows (
    principal_hash text NOT NULL,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL DEFAULT 0,
    PRIMARY KEY (principal_hash, window_started_at),
    CONSTRAINT mcp_rate_limit_windows_request_count_nonnegative
        CHECK (request_count >= 0)
);

CREATE INDEX idx_mcp_rate_limit_windows_started_at
    ON mcp_rate_limit_windows (window_started_at);

CREATE TABLE mcp_audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at timestamptz NOT NULL DEFAULT NOW(),
    principal_hash text,
    request_id text,
    event_type text NOT NULL,
    tool_name text,
    outcome text NOT NULL,
    duration_ms integer,
    error_code text,
    client_name text,
    client_version text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT mcp_audit_events_duration_nonnegative
        CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX idx_mcp_audit_events_occurred_at
    ON mcp_audit_events (occurred_at DESC);

CREATE INDEX idx_mcp_audit_events_tool_outcome
    ON mcp_audit_events (tool_name, outcome, occurred_at DESC);

COMMIT;
