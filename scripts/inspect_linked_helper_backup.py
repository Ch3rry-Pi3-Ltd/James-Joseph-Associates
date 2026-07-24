"""
Inspect a Linked Helper backup in memory without extracting personal data.

The `.lhd2` backup format is ZIP-compatible and contains an SQLite database.
This operator script reports archive metadata, table names, columns, and row
counts only. It does not persist the backup or extracted database locally.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from io import BytesIO
from typing import Any
from zipfile import BadZipFile, ZipFile

from backend.services.dropbox_api import download_dropbox_file
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    _load_dropbox_connection,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a Dropbox Linked Helper backup without extracting it."
    )
    parser.add_argument(
        "--dropbox-path",
        required=True,
        help="Full Dropbox path to the Linked Helper .lhd2 backup.",
    )
    parser.add_argument(
        "--compare-dropbox-path",
        help=(
            "Optional second backup to compare by stable identifiers only. "
            "No identifier values are printed."
        ),
    )
    parser.add_argument(
        "--compare-only",
        action="store_true",
        help=(
            "Print only archive sizes and the stable-identifier comparison. "
            "Requires --compare-dropbox-path."
        ),
    )
    return parser


def inspect_linked_helper_backup(content_bytes: bytes) -> dict[str, Any]:
    database_member_name, database_bytes, member_count = (
        _read_linked_helper_database(content_bytes)
    )

    connection = _deserialize_database(database_bytes)
    try:
        table_names = [
            str(row[0])
            for row in connection.execute(
                """
                select name
                from sqlite_master
                where type = 'table'
                  and name not like 'sqlite_%'
                order by name
                """
            )
        ]
        tables = [
            {
                "name": table_name,
                "row_count": _count_table_rows(connection, table_name),
                "columns": _list_table_columns(connection, table_name),
            }
            for table_name in table_names
        ]
        safe_statistics = _build_safe_statistics(connection)
    finally:
        connection.close()

    return {
        "downloaded_bytes": len(content_bytes),
        "downloaded_mib": round(len(content_bytes) / 1_048_576, 2),
        "archive_member_count": member_count,
        "database_member": database_member_name,
        "database_bytes": len(database_bytes),
        "database_mib": round(len(database_bytes) / 1_048_576, 2),
        "table_count": len(tables),
        "tables": tables,
        "safe_statistics": safe_statistics,
    }


def compare_linked_helper_backups(
    primary_content_bytes: bytes,
    comparison_content_bytes: bytes,
) -> dict[str, Any]:
    primary_identifiers = _collect_stable_identifier_sets(primary_content_bytes)
    comparison_identifiers = _collect_stable_identifier_sets(
        comparison_content_bytes
    )
    return {
        entity_name: {
            "primary_unique": len(primary_values),
            "comparison_unique": len(comparison_values),
            "overlap": len(primary_values & comparison_values),
            "primary_only": len(primary_values - comparison_values),
            "comparison_only": len(comparison_values - primary_values),
        }
        for entity_name, primary_values in primary_identifiers.items()
        for comparison_values in [comparison_identifiers[entity_name]]
    }


def _read_linked_helper_database(
    content_bytes: bytes,
) -> tuple[str, bytes, int]:
    try:
        with ZipFile(BytesIO(content_bytes)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            database_members = [
                member for member in members if member.filename.lower().endswith(".db")
            ]
            if len(database_members) != 1:
                raise RuntimeError(
                    "Expected exactly one SQLite database in the Linked Helper backup."
                )
            database_member = database_members[0]
            database_bytes = archive.read(database_member)
    except BadZipFile as exc:
        raise RuntimeError("Linked Helper backup is not ZIP-compatible.") from exc

    if not database_bytes.startswith(b"SQLite format 3\x00"):
        raise RuntimeError("Linked Helper database has an unexpected file signature.")

    return database_member.filename, database_bytes, len(members)


def _deserialize_database(database_bytes: bytes) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.deserialize(database_bytes)
    return connection


def _collect_stable_identifier_sets(
    content_bytes: bytes,
) -> dict[str, set[str]]:
    _, database_bytes, _ = _read_linked_helper_database(content_bytes)
    connection = _deserialize_database(database_bytes)
    try:
        return {
            "people": _column_values_if_present(
                connection,
                "people",
                "original_id",
            ),
            "public_profiles": {
                str(row[0])
                for row in (
                    connection.execute(
                        """
                        select external_id
                        from person_external_ids
                        where type_group = 'public'
                          and external_id is not null
                        """
                    )
                    if _column_exists(
                        connection,
                        "person_external_ids",
                        "external_id",
                    )
                    and _column_exists(
                        connection,
                        "person_external_ids",
                        "type_group",
                    )
                    else []
                )
            },
            "organizations": _column_values_if_present(
                connection,
                "organizations",
                "original_id",
            ),
            "chats": _column_values_if_present(
                connection,
                "chats",
                "original_id",
            ),
            "messages": _column_values_if_present(
                connection,
                "message_external_ids",
                "external_id",
            ),
        }
    finally:
        connection.close()


def _column_values_if_present(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> set[str]:
    if not _column_exists(connection, table_name, column_name):
        return set()
    return _column_values(connection, table_name, column_name)


def _column_values(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> set[str]:
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    return {
        str(row[0])
        for row in connection.execute(
            f"""
            select distinct {quoted_column}
            from {quoted_table}
            where {quoted_column} is not null
            """
        )
    }


def _count_table_rows(connection: sqlite3.Connection, table_name: str) -> int:
    quoted_table_name = _quote_identifier(table_name)
    row = connection.execute(
        f"select count(*) from {quoted_table_name}"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _list_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> list[dict[str, Any]]:
    quoted_table_name = _quote_identifier(table_name)
    return [
        {
            "name": str(row[1]),
            "type": str(row[2]),
            "nullable": not bool(row[3]),
            "primary_key": bool(row[5]),
        }
        for row in connection.execute(f"pragma table_info({quoted_table_name})")
    ]


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _build_safe_statistics(connection: sqlite3.Connection) -> dict[str, Any]:
    field_targets = (
        ("people", "original_id"),
        ("person_original_mini_profile", "full_name"),
        ("person_original_mini_profile", "headline"),
        ("person_current_position", "company"),
        ("person_current_position", "position"),
        ("person_email", "email"),
        ("person_phone_numbers", "number"),
        ("person_summary", "text"),
        ("person_connect", "connected_at"),
        ("person_positions", "title"),
        ("person_positions", "company_name"),
        ("person_positions", "company_id"),
        ("person_skill", "skill_id"),
        ("person_note", "note"),
        ("organizations", "original_id"),
        ("organization_mini_profile", "name"),
        ("organization_extra", "website"),
        ("organization_extra", "phone"),
        ("chats", "original_id"),
        ("messages", "message_text"),
    )
    enum_targets = {
        "person_external_id_type_group": (
            "person_external_ids",
            "type_group",
        ),
        "person_external_identifier_type": (
            "person_external_id_identifiers",
            "type",
        ),
        "person_email_type": ("person_email", "type"),
        "person_phone_type": ("person_phone_numbers", "type"),
        "person_phone_source": ("person_phone_numbers", "source"),
        "connection_distance": ("person_member_distance", "distance"),
        "chat_type": ("chats", "type"),
        "chat_platform": ("chats", "platform"),
        "message_type": ("messages", "type"),
    }
    date_targets = (
        ("people", "updated_at"),
        ("person_current_position", "updated_at"),
        ("person_positions", "actual_at"),
        ("person_connect", "connected_at"),
        ("messages", "send_at"),
        ("messages", "updated_at"),
    )
    relationship_tables = (
        "person_original_mini_profile",
        "person_current_position",
        "person_email",
        "person_phone_numbers",
        "person_summary",
        "person_connect",
        "person_positions",
        "person_skill",
        "person_note",
        "organization_mini_profile",
        "chat_participants",
        "participant_messages",
    )
    return {
        "field_coverage": [
            _field_coverage(connection, table_name, column_name)
            for table_name, column_name in field_targets
            if _column_exists(connection, table_name, column_name)
        ],
        "enum_counts": {
            label: _group_counts(connection, table_name, column_name)
            for label, (table_name, column_name) in enum_targets.items()
            if _column_exists(connection, table_name, column_name)
        },
        "date_ranges": [
            _date_range(connection, table_name, column_name)
            for table_name, column_name in date_targets
            if _column_exists(connection, table_name, column_name)
        ],
        "relationships": {
            table_name: _foreign_keys(connection, table_name)
            for table_name in relationship_tables
            if _table_exists(connection, table_name)
        },
    }


def _column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    if not _table_exists(connection, table_name):
        return False
    quoted_table = _quote_identifier(table_name)
    return any(
        str(row[1]) == column_name
        for row in connection.execute(f"pragma table_info({quoted_table})")
    )


def _table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = connection.execute(
        """
        select 1
        from sqlite_master
        where type = 'table'
          and name = ?
        limit 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _field_coverage(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> dict[str, Any]:
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    row = connection.execute(
        f"""
        select
            count(*) as total_count,
            count({quoted_column}) as populated_count,
            count(distinct {quoted_column}) as distinct_count
        from {quoted_table}
        """
    ).fetchone()
    total_count = int(row[0])
    populated_count = int(row[1])
    return {
        "table": table_name,
        "column": column_name,
        "total": total_count,
        "populated": populated_count,
        "distinct": int(row[2]),
        "coverage_percent": (
            round((populated_count / total_count) * 100, 2)
            if total_count > 0
            else 0.0
        ),
    }


def _group_counts(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> list[dict[str, Any]]:
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    return [
        {
            "value": "(null)" if row[0] is None else str(row[0]),
            "count": int(row[1]),
        }
        for row in connection.execute(
            f"""
            select {quoted_column}, count(*)
            from {quoted_table}
            group by {quoted_column}
            order by count(*) desc
            """
        )
    ]


def _date_range(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> dict[str, Any]:
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    row = connection.execute(
        f"""
        select min({quoted_column}), max({quoted_column})
        from {quoted_table}
        where {quoted_column} is not null
        """
    ).fetchone()
    return {
        "table": table_name,
        "column": column_name,
        "minimum": row[0],
        "maximum": row[1],
    }


def _foreign_keys(
    connection: sqlite3.Connection,
    table_name: str,
) -> list[dict[str, str]]:
    quoted_table = _quote_identifier(table_name)
    return [
        {
            "from": str(row[3]),
            "to_table": str(row[2]),
            "to_column": str(row[4]),
        }
        for row in connection.execute(f"pragma foreign_key_list({quoted_table})")
    ]


def main() -> None:
    args = build_parser().parse_args()
    if args.compare_only and not args.compare_dropbox_path:
        raise SystemExit("--compare-only requires --compare-dropbox-path.")

    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    downloaded_file = download_dropbox_file(
        access_token=str(stored_connection["access_token"]),
        path=args.dropbox_path,
        timeout_seconds=120,
    )
    result: dict[str, Any] = {
        "downloaded_mib": round(
            len(downloaded_file["content_bytes"]) / 1_048_576,
            2,
        ),
    }
    if not args.compare_only:
        result = inspect_linked_helper_backup(downloaded_file["content_bytes"])

    if args.compare_dropbox_path:
        comparison_file = download_dropbox_file(
            access_token=str(stored_connection["access_token"]),
            path=args.compare_dropbox_path,
            timeout_seconds=120,
        )
        result["comparison_downloaded_mib"] = round(
            len(comparison_file["content_bytes"]) / 1_048_576,
            2,
        )
        result["identifier_comparison"] = compare_linked_helper_backups(
            downloaded_file["content_bytes"],
            comparison_file["content_bytes"],
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
