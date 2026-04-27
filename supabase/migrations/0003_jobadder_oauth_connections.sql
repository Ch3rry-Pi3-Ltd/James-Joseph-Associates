-- Store the active JobAdder OAuth connection for one connected JobAdder account.
--
-- Why this table exists
-- ---------------------
-- The backend can now:
--
--  - build the JobAdder approval URL
--  - receive the callback
--  - exchange a one-time authorization code for tokens
--
-- But without persistence, those tokens would be lost as soon as the process
-- ends or the app restarts.
--
-- This table gives the backend a stable place to store:
--
--  - the short-lived access token
--  - the refresh token
--  - the token type
--  - the lifetime returned by JobAdder
--  - when the token was obtained
--  - the JobAdder account metadata returned alongside the token
--
-- Design choice
-- -------------
-- This table treats `jobadder_account` as the natural unique key for the
-- connected JobAdder account.
--
-- That matches the current backend helper, which upserts on:
--
--      on conflict (jobadder_account)
--
-- Important assumption
-- --------------------
-- This migration assumes the earlier schema migration already created the
-- shared `set_updated_at()` trigger function.

BEGIN;

CREATE TABLE jobadder_oauth_connections(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- JobAdder bearer token used for real API calls
    --  - This is short-lived and will later need refreshing.
    access_token text NOT NULL,

    -- Refresh token used to request a new access token later
    --  - JobAdder returns this when `offline_access` is included in the scope.
    refresh_token text,

    -- Usually "Bearer", but we store the actual returned value instead of
    -- hard-coding assumptions into the database
    token_type text NOT NULL,

    -- Lifetime returned by JobAdder, in seconds.
    --  - This is stored alongside `obtained_at` because a duration alone is not
    --    enough to calculate whether the token has expired.
    expires_in_seconds integer NOT NULL,

    -- Timestamp recording when this token set was obtained by the backend
    obtained_at timestamptz NOT NULL,

    -- Additional JobAdder metadata returned by the token response
    --  - The OAuth docs indicate these fields are returned alongside the tokens.
    api_url text,
    jobadder_instance text,

    -- Stable JobAdder account identifier associated with this token set
    --  - This is the key we use for upserts and later lookups.
    jobadder_account bigint NOT NULL,

    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),

    CONSTRAINT jobadder_oauth_connections_jobadder_account_unique
        UNIQUE (jobadder_account)
);

-- Small supporting index for instance-based filtering if needed later
CREATE INDEX idx_jobadder_oauth_connections_instance
    ON jobadder_oauth_connections (jobadder_instance);

-- Keep `updated_at` consistent whenever the row is updated through backend SQL
CREATE TRIGGER trg_jobadder_oauth_connections_updated_at
BEFORE UPDATE ON jobadder_oauth_connections
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
