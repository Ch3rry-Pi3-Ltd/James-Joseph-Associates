"""Tests for the controlled PostgreSQL export and restore workflow."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts import database_backup as subject


SOURCE_URL = "postgresql://source-user:source-secret@source.example:5432/source_db"
TARGET_URL = "postgresql://target-user:target-secret@target.example:5432/target_db"


def _fake_tool_resolver(
    tool_name: str,
    _pg_bin_dir: Path | None,
    _pg_container_image: str | None = None,
) -> str:
    return tool_name


def _export_runner(
    args: list[str],
    *,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    assert "source-secret" not in " ".join(args)
    if args[0] == "pg_dump":
        assert env["PGPASSWORD"] == "source-secret"
        output = next(value.split("=", 1)[1] for value in args if value.startswith("--file="))
        Path(output).write_bytes(b"synthetic-custom-archive")
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.CompletedProcess(
        args,
        0,
        "; archive\n1; 0 0 TABLE DATA public people postgres\n",
        "",
    )


def _write_test_archive(tmp_path: Path) -> tuple[Path, Path]:
    archive = tmp_path / "source.dump"
    archive.write_bytes(b"synthetic-custom-archive")
    migrations = subject.migration_inventory()
    manifest = {
        "format_version": subject.MANIFEST_FORMAT_VERSION,
        "archive_filename": archive.name,
        "archive_sha256": subject.sha256_file(archive),
        "source_fingerprint": subject.database_fingerprint(SOURCE_URL),
        "migration_fingerprint": subject.migration_fingerprint(migrations),
        "migrations": migrations,
        "table_counts": {"people": 2, "companies": 1},
        "table_count": 2,
        "row_count": 3,
    }
    manifest_path = archive.with_name(f"{archive.name}.manifest.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return archive, manifest_path


def test_connection_fingerprint_ignores_password() -> None:
    changed_password = SOURCE_URL.replace("source-secret", "different-secret")
    changed_user = SOURCE_URL.replace("source-user", "different-user")
    assert subject.database_fingerprint(SOURCE_URL) == subject.database_fingerprint(
        changed_password
    )
    assert subject.database_fingerprint(SOURCE_URL) == subject.database_fingerprint(
        changed_user
    )


def test_connection_fingerprint_normalizes_localhost_aliases() -> None:
    localhost_url = "postgresql://user:secret@localhost:5432/app"
    loopback_url = "postgresql://other:secret@127.0.0.1:5432/app"
    assert subject.database_fingerprint(localhost_url) == subject.database_fingerprint(
        loopback_url
    )


def test_pg_connection_keeps_password_out_of_command() -> None:
    args, env = subject._build_pg_connection(SOURCE_URL)
    assert "source-secret" not in " ".join(args)
    assert env["PGPASSWORD"] == "source-secret"


def test_docker_runner_rewrites_local_connection_and_archive_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "backup.dump"
    captured: list[list[str]] = []
    monkeypatch.setattr(subject.shutil, "which", lambda _name: "docker")

    def run_command(
        args: list[str],
        *,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        assert env["PGPASSWORD"] == "secret"
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subject, "_run_command", run_command)
    runner = subject.DockerPgCommandRunner("postgres:17")
    runner(
        [
            "pg_dump",
            "--host=127.0.0.1",
            f"--file={archive}",
        ],
        env={"PGPASSWORD": "secret"},
    )

    command = captured[0]
    assert "--host=host.docker.internal" in command
    assert "--file=/backup/backup.dump" in command
    assert "secret" not in " ".join(command)
    assert f"{tmp_path.resolve()}:/backup" in command


def test_docker_runner_rewrites_atomic_partial_archive_path(
    tmp_path: Path,
) -> None:
    partial_archive = tmp_path / "backup.dump.partial"
    rewritten, archive_directory = subject._rewrite_container_archive_paths(
        ["pg_restore", "--list", str(partial_archive)]
    )

    assert rewritten[-1] == "/backup/backup.dump.partial"
    assert archive_directory == tmp_path.resolve()


def test_migration_inventory_and_tables_are_stable() -> None:
    inventory = subject.migration_inventory()
    assert inventory[0]["name"] == "0001_enable_extensions.sql"
    assert "people" in subject.migration_table_names()
    assert "candidate_saved_briefs" in subject.migration_table_names()
    assert len(subject.migration_fingerprint(inventory)) == 64


def test_export_writes_archive_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "_resolve_pg_tool", _fake_tool_resolver)
    archive = tmp_path / "backup.dump"

    result = subject.export_database(
        source_url=SOURCE_URL,
        output_path=archive,
        command_runner=_export_runner,
        table_count_collector=lambda _url, tables: {name: 0 for name in tables},
    )

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert archive.read_bytes() == b"synthetic-custom-archive"
    assert manifest["archive_sha256"] == subject.sha256_file(archive)
    assert manifest["source_fingerprint"] == subject.database_fingerprint(SOURCE_URL)
    assert manifest["scope"] == "public-data-only"


def test_verify_rejects_tampered_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, manifest = _write_test_archive(tmp_path)
    archive.write_bytes(b"tampered")
    monkeypatch.setattr(subject, "_resolve_pg_tool", _fake_tool_resolver)

    with pytest.raises(subject.DatabaseBackupError, match="checksum"):
        subject.verify_archive(
            archive_path=archive,
            manifest_path=manifest,
            command_runner=_export_runner,
        )


def test_restore_preview_reports_target_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, manifest = _write_test_archive(tmp_path)
    monkeypatch.setattr(subject, "_resolve_pg_tool", _fake_tool_resolver)

    result = subject.restore_database(
        target_url=TARGET_URL,
        archive_path=archive,
        manifest_path=manifest,
        command_runner=_export_runner,
    )

    assert result["database_writes"] == 0
    assert result["target_fingerprint"] == subject.database_fingerprint(TARGET_URL)


def test_restore_rejects_source_database_as_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, manifest = _write_test_archive(tmp_path)
    monkeypatch.setattr(subject, "_resolve_pg_tool", _fake_tool_resolver)

    with pytest.raises(subject.DatabaseBackupError, match="source database"):
        subject.restore_database(
            target_url=SOURCE_URL,
            archive_path=archive,
            manifest_path=manifest,
            command_runner=_export_runner,
        )


def test_restore_rejects_nonempty_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, manifest = _write_test_archive(tmp_path)
    monkeypatch.setattr(subject, "_resolve_pg_tool", _fake_tool_resolver)

    with pytest.raises(subject.DatabaseBackupError, match="contains application data"):
        subject.restore_database(
            target_url=TARGET_URL,
            archive_path=archive,
            manifest_path=manifest,
            confirm_target=subject.database_fingerprint(TARGET_URL),
            execute=True,
            command_runner=_export_runner,
            target_inspector=lambda _url, _tables: {"companies": 0, "people": 1},
        )


def test_restore_executes_migrations_and_checks_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, manifest = _write_test_archive(tmp_path)
    monkeypatch.setattr(subject, "_resolve_pg_tool", _fake_tool_resolver)
    inspections = iter(
        [
            {"companies": None, "people": None},
            {"companies": 0, "people": 0},
        ]
    )
    migrations_applied: list[str] = []
    commands: list[list[str]] = []

    def runner(
        args: list[str],
        *,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        assert "target-secret" not in " ".join(args)
        if "--list" in args:
            return subprocess.CompletedProcess(args, 0, "1; TABLE DATA people\n", "")
        assert env["PGPASSWORD"] == "target-secret"
        return subprocess.CompletedProcess(args, 0, "", "")

    result = subject.restore_database(
        target_url=TARGET_URL,
        archive_path=archive,
        manifest_path=manifest,
        confirm_target=subject.database_fingerprint(TARGET_URL),
        execute=True,
        command_runner=runner,
        target_inspector=lambda _url, _tables: next(inspections),
        migration_applier=lambda url: migrations_applied.append(url),
        table_count_collector=lambda _url, _tables: {"companies": 1, "people": 2},
    )

    assert result["restored"] is True
    assert result["restored_row_count"] == 3
    assert migrations_applied == [TARGET_URL]
    assert any("--single-transaction" in command for command in commands)
