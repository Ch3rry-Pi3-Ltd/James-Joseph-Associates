"""
Unit tests for the read-only Linked Helper backup inspector.
"""

from io import BytesIO
import sqlite3
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.inspect_linked_helper_backup import (
    compare_linked_helper_backups,
    inspect_linked_helper_backup,
)


def _build_backup(*, people: list[str], profiles: list[str]) -> bytes:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        create table people (
            id text primary key,
            original_id text,
            updated_at text
        );
        create table person_external_ids (
            id text primary key,
            person_id text,
            external_id text,
            type_group text
        );
        """
    )
    connection.executemany(
        "insert into people (id, original_id) values (?, ?)",
        [(f"person-{index}", value) for index, value in enumerate(people)],
    )
    connection.executemany(
        """
        insert into person_external_ids (
            id,
            person_id,
            external_id,
            type_group
        )
        values (?, ?, ?, 'public')
        """,
        [
            (f"profile-{index}", f"person-{index}", value)
            for index, value in enumerate(profiles)
        ],
    )
    database_bytes = connection.serialize()
    connection.close()

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("lh.db", database_bytes)
    return archive_buffer.getvalue()


def test_inspect_linked_helper_backup_reports_archive_metadata() -> None:
    backup = _build_backup(people=["one"], profiles=["profile-one"])

    result = inspect_linked_helper_backup(backup)

    assert result["archive_member_count"] == 1
    assert result["database_member"] == "lh.db"
    assert result["table_count"] == 2
    assert {
        table["name"]: table["row_count"]
        for table in result["tables"]
    } == {
        "people": 1,
        "person_external_ids": 1,
    }


def test_compare_linked_helper_backups_reports_superset_without_identifiers() -> None:
    primary = _build_backup(
        people=["one", "two"],
        profiles=["profile-one", "profile-two"],
    )
    comparison = _build_backup(
        people=["one"],
        profiles=["profile-one"],
    )

    result = compare_linked_helper_backups(primary, comparison)

    assert result["people"] == {
        "primary_unique": 2,
        "comparison_unique": 1,
        "overlap": 1,
        "primary_only": 1,
        "comparison_only": 0,
    }
    assert result["public_profiles"] == {
        "primary_unique": 2,
        "comparison_unique": 1,
        "overlap": 1,
        "primary_only": 1,
        "comparison_only": 0,
    }
