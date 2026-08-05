BEGIN;

-- The application is server-only: browsers authenticate with Clerk and all
-- database access goes through the FastAPI backend. Supabase's automatic
-- `anon` and `authenticated` grants are therefore unnecessary and expose the
-- canonical recruitment data through PostgREST if RLS is not enabled.
DO $revoke_supabase_api_roles$
DECLARE
    api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
                api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
                api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I',
                api_role
            );

            -- Prevent migrations run as the normal Supabase `postgres` owner
            -- from silently reintroducing the automatic grants on new objects.
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
                'REVOKE ALL PRIVILEGES ON TABLES FROM %I',
                api_role
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
                'REVOKE ALL PRIVILEGES ON SEQUENCES FROM %I',
                api_role
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
                'REVOKE ALL PRIVILEGES ON FUNCTIONS FROM %I',
                api_role
            );
        END IF;
    END LOOP;
END
$revoke_supabase_api_roles$;

-- PostgreSQL functions are executable by PUBLIC by default. The only current
-- public-schema function is trigger-only, and the backend does not use public
-- RPC functions, so close that indirect API surface as well.
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- Apply RLS to every application table and grant unrestricted row policies
-- only to the no-login backend roles introduced by migration 0014. The login
-- used by Vercel inherits `jja_app_writer`, which itself inherits the read role.
DO $enable_backend_only_rls$
DECLARE
    target_table regclass;
BEGIN
    FOR target_table IN
        SELECT c.oid::regclass
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p')
        ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', target_table);

        EXECUTE format(
            'CREATE POLICY jja_app_readonly_select ON %s '
            'FOR SELECT TO jja_app_readonly USING (true)',
            target_table
        );
        EXECUTE format(
            'CREATE POLICY jja_app_writer_insert ON %s '
            'FOR INSERT TO jja_app_writer WITH CHECK (true)',
            target_table
        );
        EXECUTE format(
            'CREATE POLICY jja_app_writer_update ON %s '
            'FOR UPDATE TO jja_app_writer USING (true) WITH CHECK (true)',
            target_table
        );
        EXECUTE format(
            'CREATE POLICY jja_app_writer_delete ON %s '
            'FOR DELETE TO jja_app_writer USING (true)',
            target_table
        );
    END LOOP;
END
$enable_backend_only_rls$;

COMMIT;
