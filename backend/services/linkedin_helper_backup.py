"""
Read Linked Helper `.lhd2` backups without extracting them to disk.

The backup is a ZIP-compatible archive containing one SQLite database. This
module maps bounded person slices into the existing Linked Helper persistence
payload shape, but it performs no canonical writes.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from io import BytesIO
from typing import Any
from urllib.parse import quote, urlparse
from zipfile import BadZipFile, ZipFile

from backend.services.linkedin_helper_reconciliation import normalize_text_key

RELATED_ROW_BATCH_SIZE = 500


def open_linkedin_helper_backup(content_bytes: bytes) -> sqlite3.Connection:
    """Open the single SQLite database from an `.lhd2` archive in memory."""

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
            database_bytes = archive.read(database_members[0])
    except BadZipFile as exc:
        raise RuntimeError("Linked Helper backup is not ZIP-compatible.") from exc

    if not database_bytes.startswith(b"SQLite format 3\x00"):
        raise RuntimeError("Linked Helper database has an unexpected file signature.")

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.deserialize(database_bytes)
    return connection


def map_linkedin_helper_backup_people(
    content_bytes: bytes,
    *,
    limit: int | None = 100,
    offset: int = 0,
    include_profile_details: bool = True,
    import_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Map a bounded backup slice to neutral canonical-person payloads."""

    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero when provided.")
    if offset < 0:
        raise ValueError("offset must be zero or greater.")

    connection = open_linkedin_helper_backup(content_bytes)
    try:
        return map_linkedin_helper_people_from_connection(
            connection,
            limit=limit,
            offset=offset,
            include_profile_details=include_profile_details,
            import_run_id=import_run_id,
        )
    finally:
        connection.close()


def map_linkedin_helper_backup_companies(
    content_bytes: bytes,
    *,
    limit: int | None = 100,
    offset: int = 0,
    import_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Map a bounded backup slice to canonical-company candidate payloads."""

    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero when provided.")
    if offset < 0:
        raise ValueError("offset must be zero or greater.")

    connection = open_linkedin_helper_backup(content_bytes)
    try:
        return map_linkedin_helper_companies_from_connection(
            connection,
            limit=limit,
            offset=offset,
            import_run_id=import_run_id,
        )
    finally:
        connection.close()


def map_linkedin_helper_companies_from_connection(
    connection: sqlite3.Connection,
    *,
    limit: int | None = 100,
    offset: int = 0,
    import_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Map organisations from an already-open Linked Helper SQLite database."""

    organization_rows = _fetch_organizations(
        connection,
        limit=limit,
        offset=offset,
    )
    if not organization_rows:
        return []

    source_name_counts = _source_organization_name_counts(connection)
    organization_ids = [
        int(row["backup_organization_id"]) for row in organization_rows
    ]
    public_ids = _group_organization_scalar_rows(
        connection,
        organization_ids,
        """
        select organization_id, external_id as value
        from organization_external_ids
        where type_group = 'public'
          and organization_id in ({placeholders})
        order by id desc
        """,
    )
    company_ids = _group_organization_scalar_rows(
        connection,
        organization_ids,
        """
        select organization_id, external_id as value
        from organization_external_ids
        where type_group = 'company'
          and organization_id in ({placeholders})
        order by id desc
        """,
    )

    payloads: list[dict[str, Any]] = []
    for row in organization_rows:
        organization_id = int(row["backup_organization_id"])
        public_identifiers = _deduplicate_strings(
            public_ids.get(organization_id, [])
        )
        company_identifiers = _deduplicate_strings(
            company_ids.get(organization_id, [])
        )
        linkedin_url = _linkedin_company_url(
            public_identifiers=public_identifiers,
            company_identifiers=company_identifiers,
        )
        website_url = _clean_optional_string(row["website_url"])
        original_id = row["original_id"]
        stable_organization_id = (
            original_id if original_id is not None else organization_id
        )
        payloads.append(
            {
                "source_record_id": (
                    f"lhd2-organization:{stable_organization_id}"
                ),
                "source_payload": {
                    "backup_organization_id": organization_id,
                    "original_id": original_id,
                    "public_identifiers": public_identifiers,
                    "company_identifiers": company_identifiers,
                    "source_updated_at": row["source_updated_at"],
                    "phone": _clean_optional_string(row["phone"]),
                    "staff_count": row["staff_count"],
                    "staff_count_start": row["staff_count_start"],
                    "staff_count_end": row["staff_count_end"],
                    "follower_count": row["follower_count"],
                    "founded_on": row["founded_on"],
                    "source_name_count": source_name_counts.get(
                        normalize_text_key(row["name"]) or "",
                        0,
                    ),
                },
                "import_run_id": import_run_id,
                "name": _clean_optional_string(row["name"]),
                "domain": _domain_from_website(website_url),
                "website_url": website_url,
                "linkedin_url": linkedin_url,
                "industry": None,
                "size_range": _organization_size_range(row),
                "location": _clean_optional_string(row["location"]),
                "description": _clean_optional_string(row["description"]),
                "status": None,
            }
        )
    return payloads


def map_linkedin_helper_people_from_connection(
    connection: sqlite3.Connection,
    *,
    limit: int | None = 100,
    offset: int = 0,
    include_profile_details: bool = True,
    import_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Map people from an already-open Linked Helper SQLite database."""

    person_rows = _fetch_people(connection, limit=limit, offset=offset)
    if not person_rows:
        return []

    source_name_company_counts = _source_person_name_company_counts(connection)
    person_ids = [int(row["backup_person_id"]) for row in person_rows]
    public_ids = _group_scalar_rows(
        connection,
        person_ids,
        """
        select person_id, external_id as value
        from person_external_ids
        where type_group = 'public'
          and person_id in ({placeholders})
        order by id desc
        """,
    )
    member_ids = _group_scalar_rows(
        connection,
        person_ids,
        """
        select person_id, external_id as value
        from person_external_ids
        where type_group = 'member'
          and person_id in ({placeholders})
        order by id desc
        """,
    )
    emails = _group_scalar_rows(
        connection,
        person_ids,
        """
        select person_id, email as value
        from person_email
        where person_id in ({placeholders})
        order by case when type = 'business' then 0 else 1 end, id desc
        """,
    )
    phones = _group_scalar_rows(
        connection,
        person_ids,
        """
        select person_id, number as value
        from person_phone_numbers
        where person_id in ({placeholders})
        order by case when type = 'MOBILE' then 0 else 1 end, id desc
        """,
    )

    employment_history: dict[int, list[dict[str, Any]]] = defaultdict(list)
    skills: dict[int, list[str]] = defaultdict(list)
    if include_profile_details:
        employment_history = _group_dict_rows(
            connection,
            person_ids,
            """
            select
                person_id,
                title,
                company_name,
                company_id,
                start,
                start_year,
                start_month,
                end,
                end_year,
                end_month,
                location_name,
                description,
                is_default
            from person_positions
            where person_id in ({placeholders})
            order by person_id, is_default desc, start_year desc, start_month desc, id desc
            """,
            excluded_keys={"person_id"},
        )
        skills = _group_scalar_rows(
            connection,
            person_ids,
            """
            select ps.person_id, s.name as value
            from person_skill ps
            join skills s on s.id = ps.skill_id
            where ps.person_id in ({placeholders})
            order by ps.person_id, s.name collate nocase
            """,
        )

    payloads: list[dict[str, Any]] = []
    for row in person_rows:
        person_id = int(row["backup_person_id"])
        public_identifiers = _deduplicate_strings(public_ids.get(person_id, []))
        linkedin_url = _linkedin_url_from_public_identifiers(public_identifiers)
        full_name = _clean_optional_string(row["full_name"])
        first_name = _clean_optional_string(row["first_name"])
        last_name = _clean_optional_string(row["last_name"])
        if full_name is None:
            full_name = " ".join(
                value for value in (first_name, last_name) if value is not None
            ).strip() or None

        original_id = row["original_id"]
        stable_person_id = original_id if original_id is not None else person_id
        source_record_id = f"lhd2-person:{stable_person_id}"
        source_payload = {
            "backup_person_id": person_id,
            "original_id": original_id,
            "public_identifiers": public_identifiers,
            "member_identifiers": _deduplicate_strings(
                member_ids.get(person_id, [])
            ),
            "connection_degree": _clean_optional_string(row["connection_degree"]),
            "connected_at": row["connected_at"],
            "employment_history": employment_history.get(person_id, []),
            "skills": _deduplicate_strings(skills.get(person_id, [])),
            "source_updated_at": row["source_updated_at"],
            "source_name_company_count": source_name_company_counts.get(
                _normalized_name_company_key(
                    row["full_name"],
                    row["first_name"],
                    row["last_name"],
                    row["company_name"],
                )
                or "",
                0,
            ),
        }
        payloads.append(
            {
                "source_record_id": source_record_id,
                "source_payload": source_payload,
                "import_run_id": import_run_id,
                "record_kind": "candidate",
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_email": _first_clean_value(emails.get(person_id, [])),
                "primary_phone": _first_clean_value(phones.get(person_id, [])),
                "linkedin_url": linkedin_url,
                "location": _clean_optional_string(row["location"]),
                "headline": _clean_optional_string(row["headline"]),
                "summary": _clean_optional_string(row["summary"]),
                "company_name": _clean_optional_string(row["company_name"]),
                "company_domain": None,
                "company_website_url": None,
                "company_linkedin_url": None,
                "role_title": _clean_optional_string(row["role_title"]),
                "seniority": None,
                "postcode": None,
                "contact_type": None,
                "is_hiring_manager": False,
                "is_current_company": True,
                "role_start_date": None,
                "role_end_date": None,
                "candidate_status": None,
                "availability_status": None,
                "resume_updated_at": None,
                "last_contacted_at": None,
            }
        )
    return payloads


def _fetch_organizations(
    connection: sqlite3.Connection,
    *,
    limit: int | None,
    offset: int,
) -> list[sqlite3.Row]:
    query = """
        select
            o.id as backup_organization_id,
            o.original_id,
            o.updated_at as source_updated_at,
            (
                select omp.name
                from organization_mini_profile omp
                where omp.organization_id = o.id
                order by omp.actual_at desc, omp.id desc
                limit 1
            ) as name,
            (
                select oe.website
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as website_url,
            (
                select oe.phone
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as phone,
            (
                select oe.description
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as description,
            (
                select oe.staff_count
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as staff_count,
            (
                select oe.staff_count_start
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as staff_count_start,
            (
                select oe.staff_count_end
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as staff_count_end,
            (
                select oe.follower_count
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as follower_count,
            (
                select oe.founded_on
                from organization_extra oe
                where oe.organization_id = o.id
                order by oe.actual_at desc, oe.id desc
                limit 1
            ) as founded_on,
            (
                select hq.full_address
                from organization_headquarter_address hq
                where hq.organization_id = o.id
                order by hq.actual_at desc, hq.id desc
                limit 1
            ) as location
        from organizations o
        order by o.id
    """
    parameters: list[int] = []
    if limit is None:
        query += " limit -1 offset ?"
        parameters.append(offset)
    else:
        query += " limit ? offset ?"
        parameters.extend((limit, offset))
    return list(connection.execute(query, parameters))


def _source_organization_name_counts(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    rows = connection.execute(
        """
        select (
            select omp.name
            from organization_mini_profile omp
            where omp.organization_id = o.id
            order by omp.actual_at desc, omp.id desc
            limit 1
        ) as name
        from organizations o
        """
    )
    for row in rows:
        name_key = normalize_text_key(row["name"])
        if name_key:
            counts[name_key] += 1
    return dict(counts)


def _source_person_name_company_counts(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    rows = connection.execute(
        """
        select
            (
                select mp.full_name
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as full_name,
            (
                select mp.first_name
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as first_name,
            (
                select mp.last_name
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as last_name,
            (
                select cp.company
                from person_original_current_position cp
                where cp.person_id = p.id
                order by cp.actual_at desc, cp.id desc
                limit 1
            ) as company_name
        from people p
        """
    )
    for row in rows:
        key = _normalized_name_company_key(
            row["full_name"],
            row["first_name"],
            row["last_name"],
            row["company_name"],
        )
        if key:
            counts[key] += 1
    return dict(counts)


def _normalized_name_company_key(
    full_name: Any,
    first_name: Any,
    last_name: Any,
    company_name: Any,
) -> str | None:
    resolved_name = _clean_optional_string(full_name)
    if resolved_name is None:
        resolved_name = " ".join(
            value
            for value in (
                _clean_optional_string(first_name),
                _clean_optional_string(last_name),
            )
            if value
        ).strip() or None
    name_key = normalize_text_key(resolved_name)
    company_key = normalize_text_key(company_name)
    if not name_key or not company_key:
        return None
    return f"{name_key}|{company_key}"


def _fetch_people(
    connection: sqlite3.Connection,
    *,
    limit: int | None,
    offset: int,
) -> list[sqlite3.Row]:
    query = """
        select
            p.id as backup_person_id,
            p.original_id,
            p.updated_at as source_updated_at,
            (
                select mp.full_name
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as full_name,
            (
                select mp.first_name
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as first_name,
            (
                select mp.last_name
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as last_name,
            (
                select mp.headline
                from person_original_mini_profile mp
                where mp.person_id = p.id
                order by mp.actual_at desc, mp.id desc
                limit 1
            ) as headline,
            (
                select cp.company
                from person_original_current_position cp
                where cp.person_id = p.id
                order by cp.actual_at desc, cp.id desc
                limit 1
            ) as company_name,
            (
                select cp.position
                from person_original_current_position cp
                where cp.person_id = p.id
                order by cp.actual_at desc, cp.id desc
                limit 1
            ) as role_title,
            (
                select ps.text
                from person_summary ps
                where ps.person_id = p.id
                order by ps.actual_at desc, ps.id desc
                limit 1
            ) as summary,
            (
                select l.name
                from person_location pl
                join locations l on l.id = pl.location_id
                where pl.person_id = p.id
                order by pl.actual_at desc, pl.id desc
                limit 1
            ) as location,
            (
                select pmd.distance
                from person_member_distance pmd
                where pmd.person_id = p.id
                order by pmd.actual_at desc, pmd.id desc
                limit 1
            ) as connection_degree,
            (
                select pc.connected_at
                from person_connect pc
                where pc.person_id = p.id
                order by pc.actual_at desc, pc.id desc
                limit 1
            ) as connected_at
        from people p
        order by p.id
    """
    parameters: list[int] = []
    if limit is None:
        query += " limit -1 offset ?"
        parameters.append(offset)
    else:
        query += " limit ? offset ?"
        parameters.extend((limit, offset))
    return list(connection.execute(query, parameters))


def _group_scalar_rows(
    connection: sqlite3.Connection,
    person_ids: list[int],
    query_template: str,
) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for batch in _batches(person_ids, RELATED_ROW_BATCH_SIZE):
        placeholders = ", ".join("?" for _ in batch)
        query = query_template.format(placeholders=placeholders)
        for row in connection.execute(query, batch):
            value = _clean_optional_string(row["value"])
            if value is not None:
                grouped[int(row["person_id"])].append(value)
    return grouped


def _group_organization_scalar_rows(
    connection: sqlite3.Connection,
    organization_ids: list[int],
    query_template: str,
) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for batch in _batches(organization_ids, RELATED_ROW_BATCH_SIZE):
        placeholders = ", ".join("?" for _ in batch)
        query = query_template.format(placeholders=placeholders)
        for row in connection.execute(query, batch):
            value = _clean_optional_string(row["value"])
            if value is not None:
                grouped[int(row["organization_id"])].append(value)
    return grouped


def _group_dict_rows(
    connection: sqlite3.Connection,
    person_ids: list[int],
    query_template: str,
    *,
    excluded_keys: set[str],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for batch in _batches(person_ids, RELATED_ROW_BATCH_SIZE):
        placeholders = ", ".join("?" for _ in batch)
        query = query_template.format(placeholders=placeholders)
        for row in connection.execute(query, batch):
            grouped[int(row["person_id"])].append(
                {
                    key: row[key]
                    for key in row.keys()
                    if key not in excluded_keys
                }
            )
    return grouped


def _batches(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _linkedin_url_from_public_identifiers(values: list[str]) -> str | None:
    for value in values:
        cleaned = value.strip()
        if cleaned == "":
            continue
        parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
        if parsed.netloc.casefold().endswith("linkedin.com") and "/in/" in parsed.path:
            slug = parsed.path.split("/in/", 1)[1].strip("/")
            if slug:
                return f"https://www.linkedin.com/in/{quote(slug, safe='-_.~')}/"
        if "/" not in cleaned and " " not in cleaned:
            return f"https://www.linkedin.com/in/{quote(cleaned, safe='-_.~')}/"
    return None


def _linkedin_company_url(
    *,
    public_identifiers: list[str],
    company_identifiers: list[str],
) -> str | None:
    for value in [*public_identifiers, *company_identifiers]:
        cleaned = value.strip()
        if cleaned == "":
            continue
        parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
        if parsed.netloc.casefold().endswith("linkedin.com") and "/company/" in (
            parsed.path
        ):
            identifier = parsed.path.split("/company/", 1)[1].split("/", 1)[0]
        elif "/" not in cleaned and " " not in cleaned:
            identifier = cleaned
        else:
            continue
        if identifier:
            return (
                "https://www.linkedin.com/company/"
                f"{quote(identifier, safe='-_.~')}/"
            )
    return None


def _domain_from_website(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    hostname = parsed.hostname
    if hostname is None:
        return None
    normalized = hostname.casefold().strip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized or None


def _organization_size_range(row: sqlite3.Row) -> str | None:
    staff_count_start = row["staff_count_start"]
    staff_count_end = row["staff_count_end"]
    if isinstance(staff_count_start, int) and isinstance(staff_count_end, int):
        return f"{staff_count_start}-{staff_count_end}"
    staff_count = row["staff_count"]
    if isinstance(staff_count, int):
        return str(staff_count)
    return None


def _first_clean_value(values: list[str]) -> str | None:
    for value in values:
        cleaned = _clean_optional_string(value)
        if cleaned is not None:
            return cleaned
    return None


def _deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        cleaned = _clean_optional_string(value)
        if cleaned is None:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(cleaned)
    return deduplicated


def _clean_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.replace("\x00", "").strip()
    return cleaned or None


__all__ = [
    "map_linkedin_helper_backup_companies",
    "map_linkedin_helper_backup_people",
    "map_linkedin_helper_companies_from_connection",
    "map_linkedin_helper_people_from_connection",
    "open_linkedin_helper_backup",
]
