# Controlled Database Export and Restore

## Recovery contract

The repository now has a repeatable recovery path for the canonical Supabase
database:

1. tracked files in `supabase/migrations/` recreate the application schema;
2. `pg_dump` writes a custom-format, data-only archive of the `public` schema;
3. a sidecar manifest records the archive checksum, migration checksums, source
   fingerprint, and exact row count for every tracked application table;
4. `pg_restore` writes only to an explicitly configured and confirmed fresh
   target; and
5. the runner compares every restored table count with the manifest.

This design avoids treating an unreviewed production schema snapshot as source
code. It also avoids restoring Supabase-managed `auth`, `storage`, or internal
schemas into another project.

## Prerequisites

Install PostgreSQL client tools containing compatible `pg_dump` and
`pg_restore` versions. Put them on `PATH`, or pass their directory through
`--pg-bin-dir`.

Alternatively, use an already installed Docker engine and an explicit
PostgreSQL image. This machine's verified path uses `postgres:17`:

```powershell
.\.venv\Scripts\python.exe -m scripts.database_backup export `
  --pg-container-image postgres:17
```

The Docker mode mounts only the selected backup directory, passes the password
through container environment rather than arguments, and translates localhost
connections to `host.docker.internal` for disposable local recovery drills.

Use a direct/non-pooling source connection where possible. The source defaults
to `POSTGRES_URL_NON_POOLING`, with the normal backend `POSTGRES_URL` fallback.
The destination must be provided separately as `RESTORE_POSTGRES_URL`.

Database passwords are passed to PostgreSQL tools through `PGPASSWORD`; they
are not placed in process arguments, manifests, or console output.

## Export

```powershell
.\.venv\Scripts\python.exe -m scripts.database_backup export
```

The default output is timestamped under `temp/database_backups/`. That entire
directory is ignored by Git because an archive contains private recruitment
and integration data. Do not move a dump into `docs/`, attach it to an issue,
or commit it.

An explicit location can be supplied when the destination has appropriate
encryption, access control, retention, and deletion policies:

```powershell
.\.venv\Scripts\python.exe -m scripts.database_backup export `
  --output D:\SecureBackups\jja-public-data.dump
```

The export is written through a `.partial` file and becomes visible at its
final path only after `pg_dump` and archive table-of-contents validation pass.

## Verify

Verification is read-only:

```powershell
.\.venv\Scripts\python.exe -m scripts.database_backup verify `
  --archive temp\database_backups\jja-public-data-YYYYMMDDTHHMMSSZ.dump
```

It checks the archive checksum, manifest version, tracked migration
fingerprint, and `pg_restore` table of contents. Migration drift fails closed;
`--allow-migration-drift` exists only for a reviewed recovery where the exact
historical migrations have been recovered separately.

## Restore preview and execution

First provision a disposable or future owner-controlled Postgres/Supabase
target. Never point `RESTORE_POSTGRES_URL` at the current source.

```powershell
$env:RESTORE_POSTGRES_URL = '<new target connection string>'
.\.venv\Scripts\python.exe -m scripts.database_backup restore `
  --archive temp\database_backups\jja-public-data-YYYYMMDDTHHMMSSZ.dump
```

The preview performs no database writes and prints a short target fingerprint.
Execute only after checking that fingerprint:

```powershell
.\.venv\Scripts\python.exe -m scripts.database_backup restore `
  --archive temp\database_backups\jja-public-data-YYYYMMDDTHHMMSSZ.dump `
  --confirm-target '<fingerprint from preview>' `
  --execute
```

The executable restore path:

- rejects the source database as its target;
- rejects a partial application schema;
- rejects any target containing application data;
- applies all tracked migrations when the target has no application schema;
- restores in one transaction with ownership and grants excluded; and
- fails if post-restore row counts differ from the manifest.

OAuth credentials and private candidate data are part of a full application
data backup. After a transfer, rotate integration secrets as appropriate,
securely destroy transient copies, and separately configure the destination's
runtime and least-privileged roles. Supabase project ownership, billing, Auth,
Storage objects, and DNS are not transferred by this public-schema workflow.

## Test status and live boundary

Automated tests exercise archive creation, checksums, migration inventory,
password isolation, source-target separation, confirmation, non-empty-target
rejection, migration execution, single-transaction restore, and restored row
count verification.

The implementation was also exercised end to end on 2 August 2026 against a
disposable PostgreSQL 17 server with pgvector:

- all `13` tracked migrations created separate source and target schemas;
- the source held `3` synthetic rows across the canonical company, person, and
  candidate graph;
- the custom archive covered all `30` tracked application tables;
- checksum and table-of-contents validation passed;
- the no-write preview identified the separate target database;
- the confirmed restore completed in one transaction; and
- all `30` post-restore table counts matched the manifest, including the `3`
  expected synthetic rows.

The disposable container and synthetic dump were removed after verification.
No production database contents were exported during this drill.

A real production-data archive is intentionally not created merely to test the
script. The first real recovery drill should export to approved encrypted
storage and restore into a disposable database configured through
`RESTORE_POSTGRES_URL`; no real archive should enter the repository.
