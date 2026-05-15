-- Store the active Dropbox OAuth connection for one connected Dropbox account.
--
-- Why this table exists
-- ---------------------
-- The backend can now:
--
--  - build the Dropbox approval URL
--  - receive the callback
--  - exchange a one-time authorization code for tokens
--  - refresh short-lived access tokens with a stored refresh token
--
-- But without persistence, those tokens would be lost as soon as the process
-- ends or the app restarts.
--
-- This table gives the backend a stable place to store:
--
--  - the short-lived access token
--  - the refresh token
--  - the token type
--  - the lifetime returned by Dropbox
--  - when the token was obtained
--  - the scope string returned by Dropbox
--  - the Dropbox account ID associated with the token set
--
-- Design choice
-- -------------
-- This table treats `dropbox_account_id` as the natural unique key for the
-- connected Dropbox account.
--
-- That matches the current backend helper, which upserts on:
--
--      on conflict (dropbox_account_id)
--
-- Important assumption
-- --------------------
-- This migration assumes the earlier schema migration already created the
-- shared `set_updated_at()` trigger function.

BEGIN;

CREATE TABLE dropbox_oauth_connections(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Dropbox bearer token used for real API calls.
    --  - Dropbox now prefers short-lived access tokens.
    access_token text NOT NULL,

    -- Refresh token used to request a new access token later.
    --  - This is returned when the authorization request asked for
    --    `token_access_type=offline`.
    refresh_token text,

    -- Usually "bearer", but we store the actual returned value rather than
    -- hard-coding assumptions into the database.
    token_type text NOT NULL,

    -- Lifetime returned by Dropbox, in seconds.
    --  - This is stored alongside `obtained_at` because a duration alone is
    --    not enough to calculate whether the token has expired.
    expires_in_seconds integer NOT NULL,

    -- Timestamp recording when this token set was obtained by the backend.
    obtained_at timestamptz NOT NULL,

    -- Scope string returned by Dropbox for the granted token.
    scope text,

    -- Stable Dropbox account identifier associated with this token set.
    --  - This is the key we use for upserts and later lookups.
    dropbox_account_id text NOT NULL,

    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),

    CONSTRAINT dropbox_oauth_connections_dropbox_account_id_unique
        UNIQUE (dropbox_account_id)
);

-- Small supporting index for account-id-based filtering.
CREATE INDEX idx_dropbox_oauth_connections_account_id
    ON dropbox_oauth_connections (dropbox_account_id);

-- Keep `updated_at` consistent whenever the row is updated through backend SQL.
CREATE TRIGGER trg_dropbox_oauth_connections_updated_at
BEFORE UPDATE ON dropbox_oauth_connections
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
