"""Apply one explicitly named, tracked Supabase migration."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from backend.db.connection import postgres_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def resolve_migration_path(migration_name: str) -> Path:
    """Resolve a migration filename without permitting directory traversal."""

    if Path(migration_name).name != migration_name:
        raise ValueError("--migration must be a filename, not a path.")
    migration_path = (MIGRATIONS_DIR / migration_name).resolve()
    if migration_path.parent != MIGRATIONS_DIR.resolve() or not migration_path.is_file():
        raise ValueError(f"Tracked migration not found: {migration_name}")
    return migration_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration", required=True)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Required to execute the migration. Otherwise prints a read-only preview.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    migration_path = resolve_migration_path(args.migration)
    sql_text = migration_path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
    if not args.commit:
        print(
            f"migration={migration_path.name} sha256={checksum} "
            "database_writes=0"
        )
        return

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql_text)
        connection.commit()
    print(f"migration={migration_path.name} sha256={checksum} applied=true")


if __name__ == "__main__":
    main()
