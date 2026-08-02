"""Create, verify, and restore controlled PostgreSQL data archives.

The tracked Supabase migrations are the schema source of truth. Backups contain
only data from the ``public`` schema and are restored only into a fresh target
whose schema is created from those migrations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Sequence

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from backend.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
DEFAULT_BACKUP_DIR = REPO_ROOT / "temp" / "database_backups"
MANIFEST_FORMAT_VERSION = 1
_CREATE_TABLE_PATTERN = re.compile(
    r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?"
    r"(?:(?:public|\"public\")\s*\.\s*)?\"?([a-z_][a-z0-9_]*)\"?",
    flags=re.IGNORECASE,
)


class DatabaseBackupError(RuntimeError):
    """Raised when a controlled export, verification, or restore cannot proceed."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, verify, or restore a controlled database backup.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--output", type=Path, default=None)
    export_parser.add_argument("--source-env", default="POSTGRES_URL_NON_POOLING")
    export_parser.add_argument("--pg-bin-dir", type=Path, default=None)
    export_parser.add_argument("--pg-container-image", default=None)
    export_parser.add_argument("--overwrite", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--archive", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, default=None)
    verify_parser.add_argument("--pg-bin-dir", type=Path, default=None)
    verify_parser.add_argument("--pg-container-image", default=None)
    verify_parser.add_argument("--allow-migration-drift", action="store_true")

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--archive", type=Path, required=True)
    restore_parser.add_argument("--manifest", type=Path, default=None)
    restore_parser.add_argument("--target-env", default="RESTORE_POSTGRES_URL")
    restore_parser.add_argument("--confirm-target", default=None)
    restore_parser.add_argument("--execute", action="store_true")
    restore_parser.add_argument("--pg-bin-dir", type=Path, default=None)
    restore_parser.add_argument("--pg-container-image", default=None)
    restore_parser.add_argument("--allow-migration-drift", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "export":
        source_url = _read_connection_url(
            args.source_env,
            allow_settings_fallback=True,
        )
        result = export_database(
            source_url=source_url,
            output_path=args.output,
            pg_bin_dir=args.pg_bin_dir,
            pg_container_image=args.pg_container_image,
            overwrite=args.overwrite,
        )
    elif args.command == "verify":
        result = verify_archive(
            archive_path=args.archive,
            manifest_path=args.manifest,
            pg_bin_dir=args.pg_bin_dir,
            pg_container_image=args.pg_container_image,
            allow_migration_drift=args.allow_migration_drift,
        )
    else:
        target_url = _read_connection_url(args.target_env)
        result = restore_database(
            target_url=target_url,
            archive_path=args.archive,
            manifest_path=args.manifest,
            confirm_target=args.confirm_target,
            execute=args.execute,
            pg_bin_dir=args.pg_bin_dir,
            pg_container_image=args.pg_container_image,
            allow_migration_drift=args.allow_migration_drift,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


def export_database(
    *,
    source_url: str,
    output_path: Path | None = None,
    pg_bin_dir: Path | None = None,
    pg_container_image: str | None = None,
    overwrite: bool = False,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    table_count_collector: Callable[[str, Sequence[str]], dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Export public-schema data and write a checksum/count manifest."""

    archive_path = _resolve_output_path(output_path)
    manifest_path = _manifest_path_for(archive_path)
    if not overwrite and (archive_path.exists() or manifest_path.exists()):
        raise DatabaseBackupError("Backup output already exists; use --overwrite.")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = archive_path.with_name(f"{archive_path.name}.partial")
    if partial_path.exists():
        partial_path.unlink()

    pg_dump = _resolve_pg_tool("pg_dump", pg_bin_dir, pg_container_image)
    pg_restore = _resolve_pg_tool("pg_restore", pg_bin_dir, pg_container_image)
    connection_args, command_env = _build_pg_connection(source_url)
    runner = command_runner or _resolve_command_runner(pg_container_image)
    migrations = migration_inventory()
    table_names = migration_table_names()

    try:
        runner(
            [
                pg_dump,
                *connection_args,
                "--format=custom",
                "--data-only",
                "--schema=public",
                "--no-owner",
                "--no-privileges",
                f"--file={partial_path}",
            ],
            env=command_env,
        )
        if not partial_path.is_file() or partial_path.stat().st_size == 0:
            raise DatabaseBackupError("pg_dump did not create a non-empty archive.")

        toc_result = runner([pg_restore, "--list", str(partial_path)], env=command_env)
        toc_entries = _count_toc_entries(toc_result.stdout)
        if toc_entries == 0:
            raise DatabaseBackupError("The archive contains no restorable entries.")

        collect_counts = table_count_collector or collect_table_counts
        table_counts = collect_counts(source_url, table_names)
        partial_path.replace(archive_path)
        _restrict_file_permissions(archive_path)

        manifest = {
            "format_version": MANIFEST_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": "public-data-only",
            "archive_filename": archive_path.name,
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": sha256_file(archive_path),
            "source_fingerprint": database_fingerprint(source_url),
            "migration_fingerprint": migration_fingerprint(migrations),
            "migrations": migrations,
            "table_counts": table_counts,
            "table_count": len(table_counts),
            "row_count": sum(table_counts.values()),
            "toc_entries": toc_entries,
        }
        _write_json_atomically(manifest_path, manifest)
        _restrict_file_permissions(manifest_path)
    except Exception:
        if partial_path.exists():
            partial_path.unlink()
        raise

    return {
        "archive": str(archive_path),
        "manifest": str(manifest_path),
        "archive_sha256": manifest["archive_sha256"],
        "source_fingerprint": manifest["source_fingerprint"],
        "table_count": manifest["table_count"],
        "row_count": manifest["row_count"],
    }


def verify_archive(
    *,
    archive_path: Path,
    manifest_path: Path | None = None,
    pg_bin_dir: Path | None = None,
    pg_container_image: str | None = None,
    allow_migration_drift: bool = False,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Verify an archive checksum, migration contract, and table of contents."""

    resolved_archive = archive_path.resolve()
    resolved_manifest = (manifest_path or _manifest_path_for(resolved_archive)).resolve()
    if not resolved_archive.is_file():
        raise DatabaseBackupError("Backup archive does not exist.")
    if not resolved_manifest.is_file():
        raise DatabaseBackupError("Backup manifest does not exist.")

    manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    if manifest.get("format_version") != MANIFEST_FORMAT_VERSION:
        raise DatabaseBackupError("Unsupported backup manifest format version.")
    if manifest.get("archive_filename") != resolved_archive.name:
        raise DatabaseBackupError("Backup manifest does not name this archive.")

    actual_checksum = sha256_file(resolved_archive)
    if actual_checksum != manifest.get("archive_sha256"):
        raise DatabaseBackupError("Backup archive checksum does not match its manifest.")

    current_migrations = migration_inventory()
    current_fingerprint = migration_fingerprint(current_migrations)
    migration_matches = current_fingerprint == manifest.get("migration_fingerprint")
    if not migration_matches and not allow_migration_drift:
        raise DatabaseBackupError(
            "Tracked migrations differ from the backup manifest; inspect before restore."
        )

    pg_restore = _resolve_pg_tool("pg_restore", pg_bin_dir, pg_container_image)
    runner = command_runner or _resolve_command_runner(pg_container_image)
    toc_result = runner([pg_restore, "--list", str(resolved_archive)], env=os.environ.copy())
    toc_entries = _count_toc_entries(toc_result.stdout)
    if toc_entries == 0:
        raise DatabaseBackupError("The archive contains no restorable entries.")

    return {
        "archive": str(resolved_archive),
        "manifest": str(resolved_manifest),
        "archive_sha256": actual_checksum,
        "migration_fingerprint_matches": migration_matches,
        "table_count": int(manifest.get("table_count", 0)),
        "row_count": int(manifest.get("row_count", 0)),
        "toc_entries": toc_entries,
        "verified": True,
    }


def restore_database(
    *,
    target_url: str,
    archive_path: Path,
    manifest_path: Path | None = None,
    confirm_target: str | None = None,
    execute: bool = False,
    pg_bin_dir: Path | None = None,
    pg_container_image: str | None = None,
    allow_migration_drift: bool = False,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    target_inspector: Callable[[str, Sequence[str]], dict[str, int | None]] | None = None,
    migration_applier: Callable[[str], None] | None = None,
    table_count_collector: Callable[[str, Sequence[str]], dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Restore a verified data archive into an explicitly confirmed fresh target."""

    verification = verify_archive(
        archive_path=archive_path,
        manifest_path=manifest_path,
        pg_bin_dir=pg_bin_dir,
        pg_container_image=pg_container_image,
        allow_migration_drift=allow_migration_drift,
        command_runner=command_runner,
    )
    resolved_manifest = Path(verification["manifest"])
    manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    target_fingerprint = database_fingerprint(target_url)
    if target_fingerprint == manifest.get("source_fingerprint"):
        raise DatabaseBackupError("Restore target is the backup source database.")

    plan = {
        **verification,
        "target_fingerprint": target_fingerprint,
        "database_writes": 0,
        "execute_requested": bool(execute),
    }
    if not execute:
        return plan
    if confirm_target != target_fingerprint:
        raise DatabaseBackupError(
            "Restore target is not confirmed; rerun with --confirm-target "
            f"{target_fingerprint}."
        )

    table_names = sorted(str(name) for name in manifest.get("table_counts", {}))
    inspect_target = target_inspector or inspect_target_tables
    initial_state = inspect_target(target_url, table_names)
    existing_tables = {name for name, count in initial_state.items() if count is not None}
    if existing_tables and existing_tables != set(table_names):
        raise DatabaseBackupError(
            "Restore target has a partial application schema; no changes were made."
        )
    if any((count or 0) > 0 for count in initial_state.values()):
        raise DatabaseBackupError(
            "Restore target contains application data; no changes were made."
        )

    if not existing_tables:
        apply_migrations = migration_applier or apply_tracked_migrations
        apply_migrations(target_url)
        migrated_state = inspect_target(target_url, table_names)
        if set(migrated_state) != set(table_names) or any(
            count is None for count in migrated_state.values()
        ):
            raise DatabaseBackupError("Tracked migrations did not create the expected schema.")

    pg_restore = _resolve_pg_tool("pg_restore", pg_bin_dir, pg_container_image)
    connection_args, command_env = _build_pg_connection(target_url)
    runner = command_runner or _resolve_command_runner(pg_container_image)
    runner(
        [
            pg_restore,
            *connection_args,
            "--data-only",
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--single-transaction",
            str(archive_path.resolve()),
        ],
        env=command_env,
    )

    collect_counts = table_count_collector or collect_table_counts
    restored_counts = collect_counts(target_url, table_names)
    expected_counts = {
        str(name): int(count) for name, count in manifest["table_counts"].items()
    }
    if restored_counts != expected_counts:
        raise DatabaseBackupError(
            "Restore completed but table counts differ from the backup manifest."
        )

    return {
        **plan,
        "database_writes": 1,
        "restored": True,
        "restored_table_count": len(restored_counts),
        "restored_row_count": sum(restored_counts.values()),
    }


def migration_inventory() -> list[dict[str, str]]:
    migrations = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        migrations.append({"name": path.name, "sha256": sha256_file(path)})
    if not migrations:
        raise DatabaseBackupError("No tracked Supabase migrations were found.")
    return migrations


def migration_fingerprint(migrations: Sequence[dict[str, str]]) -> str:
    payload = json.dumps(list(migrations), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def migration_table_names() -> list[str]:
    names: set[str] = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        names.update(_CREATE_TABLE_PATTERN.findall(path.read_text(encoding="utf-8")))
    if not names:
        raise DatabaseBackupError("Tracked migrations define no application tables.")
    return sorted(name.lower() for name in names)


def collect_table_counts(connection_url: str, table_names: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with psycopg.connect(connection_url) as connection:
        with connection.cursor() as cursor:
            for table_name in table_names:
                cursor.execute(
                    sql.SQL("select count(*) from public.{}").format(
                        sql.Identifier(table_name)
                    )
                )
                row = cursor.fetchone()
                counts[table_name] = int(row[0])
    return counts


def inspect_target_tables(
    connection_url: str,
    table_names: Sequence[str],
) -> dict[str, int | None]:
    existing_counts: dict[str, int | None] = {name: None for name in table_names}
    with psycopg.connect(connection_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_type = 'BASE TABLE'
                """
            )
            existing = {str(row[0]) for row in cursor.fetchall()}
            for table_name in table_names:
                if table_name not in existing:
                    continue
                cursor.execute(
                    sql.SQL("select count(*) from public.{}").format(
                        sql.Identifier(table_name)
                    )
                )
                row = cursor.fetchone()
                existing_counts[table_name] = int(row[0])
    return existing_counts


def apply_tracked_migrations(connection_url: str) -> None:
    with psycopg.connect(connection_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                cursor.execute(migration_path.read_text(encoding="utf-8"))


def database_fingerprint(connection_url: str) -> str:
    parameters = conninfo_to_dict(connection_url)
    host = str(parameters.get("host", "")).strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "localhost"
    identity = {
        "host": host,
        "port": parameters.get("port", "5432"),
        "dbname": parameters.get("dbname", ""),
    }
    encoded = json.dumps(identity, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_connection_url(env_name: str, *, allow_settings_fallback: bool = False) -> str:
    connection_url = os.getenv(env_name, "").strip()
    if connection_url == "" and allow_settings_fallback:
        connection_url = get_settings().postgres_url.strip()
    if connection_url == "":
        raise DatabaseBackupError(f"Database URL environment variable is empty: {env_name}")
    return connection_url


def _resolve_output_path(output_path: Path | None) -> Path:
    if output_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = DEFAULT_BACKUP_DIR / f"jja-public-data-{timestamp}.dump"
    resolved = output_path.resolve()
    if resolved.suffix.lower() != ".dump":
        raise DatabaseBackupError("Backup output must use the .dump extension.")
    return resolved


def _manifest_path_for(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}.manifest.json")


def _resolve_pg_tool(
    tool_name: str,
    pg_bin_dir: Path | None,
    pg_container_image: str | None = None,
) -> str:
    if pg_container_image is not None:
        if pg_bin_dir is not None:
            raise DatabaseBackupError(
                "Use either --pg-bin-dir or --pg-container-image, not both."
            )
        return tool_name
    executable_name = f"{tool_name}.exe" if os.name == "nt" else tool_name
    if pg_bin_dir is not None:
        candidate = (pg_bin_dir / executable_name).resolve()
        if not candidate.is_file():
            raise DatabaseBackupError(f"PostgreSQL tool not found: {candidate}")
        return str(candidate)
    located = shutil.which(tool_name)
    if located is None:
        raise DatabaseBackupError(
            f"{tool_name} is not installed or not on PATH. Use --pg-bin-dir."
        )
    return located


def _resolve_command_runner(
    pg_container_image: str | None,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    if pg_container_image is None:
        return _run_command
    return DockerPgCommandRunner(pg_container_image)


class DockerPgCommandRunner:
    """Run PostgreSQL client commands in an ephemeral Docker container."""

    def __init__(self, image: str) -> None:
        normalized_image = image.strip()
        if normalized_image == "":
            raise DatabaseBackupError("PostgreSQL container image cannot be blank.")
        docker = shutil.which("docker")
        if docker is None:
            raise DatabaseBackupError("Docker is not installed or not on PATH.")
        self.image = normalized_image
        self.docker = docker

    def __call__(
        self,
        args: Sequence[str],
        *,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        rewritten_args, archive_directory = _rewrite_container_archive_paths(args)
        docker_args = [self.docker, "run", "--rm"]
        if archive_directory is not None:
            docker_args.extend(
                ["--volume", f"{archive_directory}:/backup"]
            )
        for variable in ("PGPASSWORD", "PGSSLMODE"):
            if env.get(variable):
                docker_args.extend(["--env", variable])
        docker_args.extend([self.image, *rewritten_args])
        return _run_command(docker_args, env=env)


def _rewrite_container_archive_paths(
    args: Sequence[str],
) -> tuple[list[str], Path | None]:
    rewritten: list[str] = []
    archive_directory: Path | None = None
    for index, raw_arg in enumerate(args):
        arg = str(raw_arg)
        if arg.startswith("--host="):
            host = arg.split("=", 1)[1].strip().lower()
            if host in {"127.0.0.1", "localhost", "::1"}:
                arg = "--host=host.docker.internal"
        path_value: str | None = None
        path_prefix = ""
        if arg.startswith("--file="):
            path_prefix = "--file="
            path_value = arg.split("=", 1)[1]
        elif index > 0 and ".dump" in Path(arg).name.lower():
            path_value = arg

        if path_value is not None:
            archive_path = Path(path_value).resolve()
            if archive_directory is None:
                archive_directory = archive_path.parent
            elif archive_directory != archive_path.parent:
                raise DatabaseBackupError(
                    "Docker PostgreSQL commands require one archive directory."
                )
            arg = f"{path_prefix}/backup/{archive_path.name}"
        rewritten.append(arg)
    return rewritten, archive_directory


def _build_pg_connection(connection_url: str) -> tuple[list[str], dict[str, str]]:
    parameters = conninfo_to_dict(connection_url)
    required = ("host", "dbname", "user")
    missing = [name for name in required if not parameters.get(name)]
    if missing:
        raise DatabaseBackupError(
            "Database connection is missing required fields: " + ", ".join(missing)
        )
    args = [
        f"--host={parameters['host']}",
        f"--port={parameters.get('port', '5432')}",
        f"--username={parameters['user']}",
        f"--dbname={parameters['dbname']}",
    ]
    command_env = os.environ.copy()
    if parameters.get("password"):
        command_env["PGPASSWORD"] = parameters["password"]
    if parameters.get("sslmode"):
        command_env["PGSSLMODE"] = parameters["sslmode"]
    return args, command_env


def _run_command(
    args: Sequence[str],
    *,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(args),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        tool_name = Path(str(args[0])).name
        stderr = (exc.stderr or "").strip()[-2000:]
        raise DatabaseBackupError(
            f"{tool_name} failed with exit code {exc.returncode}: {stderr}"
        ) from exc


def _count_toc_entries(toc_text: str) -> int:
    return sum(
        1
        for line in toc_text.splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    )


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    partial_path = path.with_name(f"{path.name}.partial")
    partial_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    partial_path.replace(path)


def _restrict_file_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        # Windows ACLs and some mounted filesystems do not implement POSIX modes.
        return


if __name__ == "__main__":
    main()
