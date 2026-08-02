# **Supabase Schema**

This folder contains source-controlled Supabase database assets for the recruitment intelligence system.

The goal is to make database changes reviewable, repeatable, and tied to the application code that depends on them.

## **Structure**

```text
supabase/
  migrations/  -> ordered SQL migrations
  seeds/       -> safe development seed data
```

## **Backup and Recovery**

Use `scripts/database_backup.py` for controlled public-schema data exports,
archive verification, and fresh-target restores. The safety contract and
operator commands are documented in `docs/database_export_restore.md`. Real
database dumps belong in the ignored `temp/database_backups/` directory or an
approved encrypted store, never in this repository.
