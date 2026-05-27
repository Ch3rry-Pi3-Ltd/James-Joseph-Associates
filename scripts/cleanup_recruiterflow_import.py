"""
Delete Recruiterflow-imported canonical rows that were loaded for the static-import proof.

This script is intentionally narrow. It removes the Recruiterflow batch-import
footprint from Supabase without touching earlier JobAdder, Dropbox, or Outlook
proof data.

The cleanup rule is conservative:

- delete Recruiterflow `source_records`
- delete canonical rows only when they are linked exclusively to Recruiterflow
  source records
- leave any canonical row in place if it also has non-Recruiterflow provenance

That matters because canonical entities such as `people` or `candidates` may
later be shared across sources. Blindly deleting every row reachable from a
Recruiterflow source record would risk removing earlier proof data as the model
converges.

Examples
--------
Dry-run the cleanup and print the rows that would be removed:

    .\\.venv\\Scripts\\python.exe -m scripts.cleanup_recruiterflow_import

Execute the cleanup against the live database:

    .\\.venv\\Scripts\\python.exe -m scripts.cleanup_recruiterflow_import --execute
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.db.connection import postgres_connection

ARTIFACT_PATH = Path("temp/recruiterflow_cleanup_report.json")


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the Recruiterflow cleanup script.

    Returns
    -------
    argparse.Namespace
        Parsed CLI arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Delete Recruiterflow-imported canonical rows that are backed only "
            "by Recruiterflow provenance."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the DELETE statements instead of only reporting the target rows.",
    )
    return parser.parse_args()


def build_cleanup_report(*, execute: bool) -> dict[str, Any]:
    """
    Inspect or delete the Recruiterflow import footprint.

    Parameters
    ----------
    execute : bool
        When `True`, run the cleanup transaction. When `False`, return the same
        report in dry-run mode.

    Returns
    -------
    dict[str, Any]
        Cleanup report containing the affected-row counts before deletion and,
        when executed, the remaining top-level canonical counts afterwards.
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(_cleanup_report_query())
            pre_cleanup = dict(cursor.fetchone() or {})

            post_cleanup: dict[str, Any] | None = None
            if execute:
                for statement in _cleanup_delete_statements():
                    cursor.execute(statement)
                cursor.execute(_remaining_counts_query())
                post_cleanup = dict(cursor.fetchone() or {})
                connection.commit()
            else:
                connection.rollback()

    return {
        "mode": "execute" if execute else "dry_run",
        "recruiterflow_cleanup_targets": pre_cleanup,
        "remaining_counts": post_cleanup,
    }


def _cleanup_report_query() -> str:
    """
    Return the read-only report query for the Recruiterflow cleanup scope.

    Returns
    -------
    str
        SQL query that reports the exclusive Recruiterflow footprint.
    """

    return """
with recruiterflow_source_records as (
    select id
    from source_records
    where source_system = 'recruiterflow'
),
exclusive_documents as (
    select distinct srl.document_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.document_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.document_id = srl.document_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_applications as (
    select distinct srl.application_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.application_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.application_id = srl.application_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_jobs as (
    select distinct srl.job_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.job_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.job_id = srl.job_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_candidates as (
    select distinct srl.candidate_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.candidate_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.candidate_id = srl.candidate_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_people as (
    select distinct srl.person_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.person_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.person_id = srl.person_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_companies as (
    select distinct srl.company_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.company_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.company_id = srl.company_id
            and other_sr.source_system <> 'recruiterflow'
      )
)
select
    (select count(*)::int from recruiterflow_source_records) as recruiterflow_source_records,
    (select count(*)::int from exclusive_documents) as documents_to_delete,
    (select count(*)::int from exclusive_applications) as applications_to_delete,
    (select count(*)::int from exclusive_jobs) as jobs_to_delete,
    (select count(*)::int from exclusive_candidates) as candidates_to_delete,
    (select count(*)::int from exclusive_people) as people_to_delete,
    (select count(*)::int from exclusive_companies) as companies_to_delete
;
"""


def _cleanup_cte_prefix() -> str:
    """
    Return the shared CTE prefix for the Recruiterflow cleanup statements.

    Returns
    -------
    str
        SQL prefix that defines the Recruiterflow-exclusive entity sets.
    """

    return """
with recruiterflow_source_records as (
    select id
    from source_records
    where source_system = 'recruiterflow'
),
exclusive_documents as (
    select distinct srl.document_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.document_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.document_id = srl.document_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_applications as (
    select distinct srl.application_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.application_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.application_id = srl.application_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_jobs as (
    select distinct srl.job_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.job_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.job_id = srl.job_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_candidates as (
    select distinct srl.candidate_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.candidate_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.candidate_id = srl.candidate_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_people as (
    select distinct srl.person_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.person_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.person_id = srl.person_id
            and other_sr.source_system <> 'recruiterflow'
      )
),
exclusive_companies as (
    select distinct srl.company_id as id
    from source_record_links srl
    join recruiterflow_source_records rsr
      on rsr.id = srl.source_record_id
    where srl.company_id is not null
      and not exists (
          select 1
          from source_record_links other_srl
          join source_records other_sr
            on other_sr.id = other_srl.source_record_id
          where other_srl.company_id = srl.company_id
            and other_sr.source_system <> 'recruiterflow'
      )
)
"""


def _cleanup_delete_statements() -> list[str]:
    """
    Return the destructive cleanup statements for the Recruiterflow footprint.

    Returns
    -------
    list[str]
        Ordered SQL DELETE statements.
    """

    prefix = _cleanup_cte_prefix()
    return [
        prefix
        + """
delete from documents
where id in (select id from exclusive_documents)
""",
        prefix
        + """
delete from applications
where id in (select id from exclusive_applications)
""",
        prefix
        + """
delete from candidates
where id in (select id from exclusive_candidates)
""",
        prefix
        + """
delete from people
where id in (select id from exclusive_people)
""",
        prefix
        + """
delete from jobs
where id in (select id from exclusive_jobs)
""",
        prefix
        + """
delete from companies
where id in (select id from exclusive_companies)
  and not exists (select 1 from candidates where current_company_id = companies.id)
  and not exists (select 1 from jobs where company_id = companies.id)
  and not exists (select 1 from contacts where company_id = companies.id)
  and not exists (select 1 from placements where company_id = companies.id)
  and not exists (select 1 from opportunities where company_id = companies.id)
""",
        """
delete from source_records
where source_system = 'recruiterflow'
""",
    ]


def _remaining_counts_query() -> str:
    """
    Return the canonical top-level counts query used after cleanup.

    Returns
    -------
    str
        SQL query returning the remaining row counts for key tables.
    """

    return """
select
    (select count(*)::int from people) as people,
    (select count(*)::int from candidates) as candidates,
    (select count(*)::int from jobs) as jobs,
    (select count(*)::int from applications) as applications,
    (select count(*)::int from documents) as documents,
    (select count(*)::int from source_records) as source_records
;
"""


def main() -> None:
    """
    Run the Recruiterflow cleanup in dry-run or execute mode.
    """

    args = parse_args()
    report = build_cleanup_report(execute=bool(args.execute))

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"artifact: {ARTIFACT_PATH}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
