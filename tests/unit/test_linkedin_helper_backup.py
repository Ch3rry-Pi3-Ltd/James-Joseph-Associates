"""Tests for reading Linked Helper `.lhd2` backups."""

from __future__ import annotations

import sqlite3
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.services.linkedin_helper_backup import (
    map_linkedin_helper_backup_companies,
    map_linkedin_helper_backup_people,
    map_linkedin_helper_companies_from_connection,
    map_linkedin_helper_people_from_connection,
    open_linkedin_helper_backup,
)


def _build_linkedin_helper_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        create table people (
            id integer primary key,
            original_id text,
            updated_at text
        );
        create table person_original_mini_profile (
            id integer primary key,
            person_id integer,
            first_name text,
            last_name text,
            full_name text,
            headline text,
            actual_at text
        );
        create table person_original_current_position (
            id integer primary key,
            person_id integer,
            company text,
            position text,
            actual_at text
        );
        create table person_summary (
            id integer primary key,
            person_id integer,
            text text,
            actual_at text
        );
        create table locations (
            id integer primary key,
            name text
        );
        create table person_location (
            id integer primary key,
            person_id integer,
            location_id integer,
            actual_at text
        );
        create table person_member_distance (
            id integer primary key,
            person_id integer,
            distance text,
            actual_at text
        );
        create table person_connect (
            id integer primary key,
            person_id integer,
            connected_at text,
            actual_at text
        );
        create table person_external_ids (
            id integer primary key,
            person_id integer,
            external_id text,
            type_group text
        );
        create table person_email (
            id integer primary key,
            person_id integer,
            email text,
            type text
        );
        create table person_phone_numbers (
            id integer primary key,
            person_id integer,
            number text,
            type text
        );
        create table person_positions (
            id integer primary key,
            person_id integer,
            title text,
            company_name text,
            company_id text,
            start text,
            start_year integer,
            start_month integer,
            end text,
            end_year integer,
            end_month integer,
            location_name text,
            description text,
            is_default integer
        );
        create table skills (
            id integer primary key,
            name text
        );
        create table person_skill (
            id integer primary key,
            person_id integer,
            skill_id integer
        );
        create table organizations (
            id integer primary key,
            original_id integer,
            created_at text,
            updated_at text
        );
        create table organization_mini_profile (
            id integer primary key,
            organization_id integer,
            name text,
            actual_at text
        );
        create table organization_external_ids (
            id integer primary key,
            organization_id integer,
            external_id text,
            type_group text
        );
        create table organization_extra (
            id integer primary key,
            organization_id integer,
            description text,
            website text,
            phone text,
            staff_count integer,
            staff_count_start integer,
            staff_count_end integer,
            follower_count integer,
            founded_on integer,
            actual_at text
        );
        create table organization_headquarter_address (
            id integer primary key,
            organization_id integer,
            full_address text,
            actual_at text
        );

        insert into people values (1, 'member-123', '2026-07-10T12:00:00Z');
        insert into person_original_mini_profile values (
            1, 1, 'Ada', 'Lovelace', 'Ada Lovelace',
            'Principal Data Engineer', '2026-07-10T12:00:00Z'
        );
        insert into person_original_current_position values (
            1, 1, 'Analytical Engines Ltd', 'Principal Data Engineer',
            '2026-07-10T12:00:00Z'
        );
        insert into person_summary values (
            1, 1, 'Builds reliable analytical systems.',
            '2026-07-10T12:00:00Z'
        );
        insert into locations values (1, 'London, United Kingdom');
        insert into person_location values (
            1, 1, 1, '2026-07-10T12:00:00Z'
        );
        insert into person_member_distance values (
            1, 1, '1', '2026-07-10T12:00:00Z'
        );
        insert into person_connect values (
            1, 1, '2025-06-01T09:30:00Z', '2026-07-10T12:00:00Z'
        );
        insert into person_external_ids values (
            1, 1, 'ada-lovelace-123', 'public'
        );
        insert into person_external_ids values (
            2, 1, 'urn:li:member:123', 'member'
        );
        insert into person_email values (
            1, 1, 'ada@example.com', 'business'
        );
        insert into person_phone_numbers values (
            1, 1, '+44 7700 900123', 'MOBILE'
        );
        insert into person_positions values (
            1, 1, 'Principal Data Engineer', 'Analytical Engines Ltd',
            'company-1', '2024-01', 2024, 1, null, null, null, 'London',
            'Data platform leadership', 1
        );
        insert into skills values (1, 'Python');
        insert into skills values (2, 'SQL');
        insert into person_skill values (1, 1, 1);
        insert into person_skill values (2, 1, 2);

        insert into organizations values (
            1, 987654, '2026-07-01T12:00:00Z', '2026-07-10T12:00:00Z'
        );
        insert into organization_mini_profile values (
            1, 1, 'Analytical Engines Ltd', '2026-07-10T12:00:00Z'
        );
        insert into organization_external_ids values (
            1, 1, 'analytical-engines', 'public'
        );
        insert into organization_external_ids values (
            2, 1, '987654', 'company'
        );
        insert into organization_extra values (
            1, 1, 'Analytical systems company.', 'https://www.example.com/about',
            '+44 20 7000 0000', 120, 101, 200, 1500, 2020,
            '2026-07-10T12:00:00Z'
        );
        insert into organization_headquarter_address values (
            1, 1, 'London, United Kingdom', '2026-07-10T12:00:00Z'
        );
        """
    )
    return connection


def _archive_database(connection: sqlite3.Connection) -> bytes:
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("lh.db", connection.serialize())
    return archive_buffer.getvalue()


def test_map_linkedin_helper_people_maps_neutral_profile_and_details() -> None:
    connection = _build_linkedin_helper_database()
    try:
        payloads = map_linkedin_helper_people_from_connection(
            connection,
            limit=10,
            include_profile_details=True,
            import_run_id="test-run",
        )
    finally:
        connection.close()

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["record_kind"] == "person"
    assert payload["source_record_id"] == "lhd2-person:member-123"
    assert payload["full_name"] == "Ada Lovelace"
    assert payload["primary_email"] == "ada@example.com"
    assert payload["primary_phone"] == "+44 7700 900123"
    assert payload["linkedin_url"] == "https://www.linkedin.com/in/ada-lovelace-123/"
    assert payload["company_name"] == "Analytical Engines Ltd"
    assert payload["role_title"] == "Principal Data Engineer"
    assert payload["location"] == "London, United Kingdom"
    assert payload["source_payload"]["skills"] == ["Python", "SQL"]
    assert payload["source_payload"]["employment_history"][0]["is_default"] == 1
    assert payload["source_payload"]["source_name_company_count"] == 1


def test_open_and_map_linkedin_helper_archive_without_disk_extraction() -> None:
    source_connection = _build_linkedin_helper_database()
    try:
        archive_bytes = _archive_database(source_connection)
    finally:
        source_connection.close()

    mapped = map_linkedin_helper_backup_people(
        archive_bytes,
        limit=1,
        include_profile_details=False,
    )

    assert mapped[0]["full_name"] == "Ada Lovelace"
    assert mapped[0]["source_payload"]["skills"] == []
    assert mapped[0]["source_payload"]["employment_history"] == []

    opened_connection = open_linkedin_helper_backup(archive_bytes)
    try:
        assert opened_connection.execute("select count(*) from people").fetchone()[0] == 1
    finally:
        opened_connection.close()


def test_open_linkedin_helper_backup_rejects_non_archive_content() -> None:
    with pytest.raises(RuntimeError, match="not ZIP-compatible"):
        open_linkedin_helper_backup(b"not a linked helper backup")


def test_map_linkedin_helper_companies_maps_stable_company_identity() -> None:
    connection = _build_linkedin_helper_database()
    try:
        payloads = map_linkedin_helper_companies_from_connection(
            connection,
            limit=10,
            import_run_id="company-test-run",
        )
    finally:
        connection.close()

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["source_record_id"] == "lhd2-organization:987654"
    assert payload["name"] == "Analytical Engines Ltd"
    assert payload["domain"] == "example.com"
    assert payload["website_url"] == "https://www.example.com/about"
    assert (
        payload["linkedin_url"]
        == "https://www.linkedin.com/company/analytical-engines/"
    )
    assert payload["size_range"] == "101-200"
    assert payload["location"] == "London, United Kingdom"
    assert payload["source_payload"]["company_identifiers"] == ["987654"]
    assert payload["source_payload"]["source_name_count"] == 1


def test_map_linkedin_helper_company_archive_without_disk_extraction() -> None:
    source_connection = _build_linkedin_helper_database()
    try:
        archive_bytes = _archive_database(source_connection)
    finally:
        source_connection.close()

    mapped = map_linkedin_helper_backup_companies(archive_bytes, limit=1)

    assert mapped[0]["name"] == "Analytical Engines Ltd"
    assert mapped[0]["source_payload"]["backup_organization_id"] == 1
