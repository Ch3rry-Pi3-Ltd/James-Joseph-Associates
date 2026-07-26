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


def _build_classification_backup() -> bytes:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        create table people (
            id integer primary key
        );
        create table campaigns (
            id integer primary key,
            name text
        );
        create table person_in_campaigns_history (
            id integer primary key,
            person_id integer,
            campaign_id integer
        );
        create table action_target_people (
            id integer primary key,
            person_id integer
        );
        create table collections (
            id integer primary key,
            name text
        );
        create table collection_people (
            id integer primary key,
            collection_id integer,
            person_id integer
        );
        create table tags (
            id integer primary key,
            title text
        );
        create table person_tag (
            id integer primary key,
            person_id integer,
            tag_id integer
        );

        insert into people values (1), (2), (3);
        insert into campaigns values
            (1, 'Rust candidates'),
            (2, 'Hiring managers');
        insert into person_in_campaigns_history values
            (1, 1, 1),
            (2, 2, 1),
            (3, 2, 2);
        insert into action_target_people values
            (1, 1),
            (2, 1),
            (3, 3);
        insert into collections values (1, 'Priority');
        insert into collection_people values (1, 1, 2);
        """
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


def test_inspect_linked_helper_backup_reports_classification_signals() -> None:
    result = inspect_linked_helper_backup(
        _build_classification_backup(),
        include_classification_signals=True,
    )

    assert result["classification_signals"] == {
        "people_total": 3,
        "campaigns_total": 2,
        "campaign_history_rows": 3,
        "distinct_people_in_campaign_history": 2,
        "campaign_people_coverage_percent": 66.67,
        "action_target_rows": 3,
        "distinct_action_target_people": 2,
        "collections_total": 1,
        "collection_people_rows": 1,
        "distinct_collection_people": 1,
        "tags_total": 0,
        "person_tag_rows": 0,
        "top_campaigns": [
            {
                "campaign_name": "Rust candidates",
                "distinct_people": 2,
            },
            {
                "campaign_name": "Hiring managers",
                "distinct_people": 1,
            },
        ],
        "top_collections": [
            {
                "collection_name": "Priority",
                "distinct_people": 1,
            }
        ],
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
