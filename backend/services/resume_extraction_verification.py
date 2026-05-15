"""
Service helpers for verifying persisted accepted resume-extraction writes.

This module sits above the narrow DB snapshot helper and turns raw verification
reads into a structured operator-facing report.

Why this module exists
----------------------
The current project state has moved beyond "can we extract?" and "can we
persist?".

The next operational question is:

    "Can we verify that the accepted JobAdder CV write actually landed in the
    canonical schema the way we expected before we bulk-load more data?"

This module answers that question without forcing scripts or future routes to
recreate ad hoc verification logic.

Important scope boundary
------------------------
This is not a full audit or observability subsystem. It verifies only the
first narrow accepted-output persistence slice:

- person
- candidate
- current company
- resume document
- source records
- source-record links
- document links
- candidate skills
- JobAdder candidate-note interactions
- note interaction participants

Example
-------
Typical service usage looks like:

    from backend.services.resume_extraction_verification import (
        verify_persisted_resume_extraction_result,
    )

    verification = verify_persisted_resume_extraction_result(
        persistence_result=persisted_summary,
    )

    print(verification.verification_passed)
    print(verification.checks[0].name)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.db.resume_extraction_verification import (
    get_resume_extraction_persistence_snapshot,
)


class PersistenceVerificationCheck(BaseModel):
    """
    One verification check outcome.

    Example
    -------
    A successful check may look like:

        PersistenceVerificationCheck(
            name="candidate_profile_exists",
            passed=True,
            details="Candidate profile row was found for the expected candidate ID.",
        )
    """

    name: str
    passed: bool
    details: str


class ResumeExtractionPersistenceVerification(BaseModel):
    """
    Structured verification report for one persisted extraction write.

    Notes
    -----
    The report is intentionally operator-facing. It keeps:

    - the expected IDs from the persistence summary
    - a list of explicit pass/fail checks
    - the raw persisted snapshot used to derive those checks

    Example
    -------
    A caller can inspect:

        report.verification_passed
        report.passed_check_count
        report.failed_check_count
        report.checks
    """

    verification_passed: bool
    passed_check_count: int
    failed_check_count: int
    expected: dict[str, Any]
    checks: list[PersistenceVerificationCheck] = Field(default_factory=list)
    snapshot: dict[str, Any]


def verify_persisted_resume_extraction_result(
    *,
    persistence_result: dict[str, Any],
) -> ResumeExtractionPersistenceVerification:
    """
    Verify one persisted accepted-output write against canonical Postgres state.

    Parameters
    ----------
    persistence_result : dict[str, Any]
        Persistence summary returned by the accepted-output write path.

    Returns
    -------
    ResumeExtractionPersistenceVerification
        Structured verification report describing whether the expected rows and
        links were found.

    Notes
    -----
    This helper is intentionally strict about the persistence summary because
    it is meant to verify an actual write result, not guess one from partial
    data later.

    Example
    -------
    A caller can verify the summary returned by persistence directly:

        report = verify_persisted_resume_extraction_result(
            persistence_result={
                "candidate_id": "...",
                "person_id": "...",
                "document_id": "...",
            }
        )
    """

    expected = _validate_and_normalize_persistence_result(persistence_result)
    snapshot = get_resume_extraction_persistence_snapshot(**expected)
    checks = _build_verification_checks(
        expected=expected,
        snapshot=snapshot,
        expected_skill_count=persistence_result.get("candidate_skill_count"),
    )

    failed_check_count = sum(1 for check in checks if not check.passed)
    passed_check_count = len(checks) - failed_check_count

    return ResumeExtractionPersistenceVerification(
        verification_passed=failed_check_count == 0,
        passed_check_count=passed_check_count,
        failed_check_count=failed_check_count,
        expected=expected,
        checks=checks,
        snapshot=snapshot,
    )


def _validate_and_normalize_persistence_result(
    persistence_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate the minimum persistence summary required for verification.

    Example
    -------
    A valid input must contain at least:

        {
            "candidate_id": "...",
            "person_id": "...",
            "candidate_source_record_id": "...",
            "extraction_source_record_id": "...",
        }
    """

    required_keys = (
        "candidate_id",
        "person_id",
        "candidate_source_record_id",
        "extraction_source_record_id",
    )
    normalized: dict[str, Any] = {}

    for key in required_keys:
        value = persistence_result.get(key)
        if not isinstance(value, str) or value.strip() == "":
            raise RuntimeError(
                f"Persistence verification requires a non-empty `{key}` value."
            )
        normalized[key] = value

    for optional_key in (
        "current_company_id",
        "document_id",
        "resume_source_record_id",
    ):
        optional_value = persistence_result.get(optional_key)
        normalized[optional_key] = (
            optional_value
            if isinstance(optional_value, str) and optional_value.strip() != ""
            else None
        )

    note_interaction_count = persistence_result.get("candidate_note_interaction_count")
    normalized["candidate_note_interaction_count"] = (
        note_interaction_count
        if isinstance(note_interaction_count, int)
        else None
    )

    return normalized


def _build_verification_checks(
    *,
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    expected_skill_count: Any,
) -> list[PersistenceVerificationCheck]:
    """
    Build the explicit pass/fail checks for one persisted snapshot.

    Notes
    -----
    These checks stay intentionally concrete. The goal is not to infer deep
    business correctness. The goal is to prove that the first persistence slice
    wrote the rows and links it claimed to write.
    """

    candidate_profile = snapshot.get("candidate_profile")
    current_company = snapshot.get("current_company")
    resume_document = snapshot.get("resume_document")
    source_records = snapshot.get("source_records", [])
    source_record_links = snapshot.get("source_record_links", [])
    document_links = snapshot.get("document_links", [])
    candidate_skills = snapshot.get("candidate_skills", [])
    candidate_note_interactions = snapshot.get("candidate_note_interactions", [])
    interaction_participants = snapshot.get("interaction_participants", [])

    # Keep the checks explicit and named rather than collapsing everything into
    # one boolean too early.
    #
    # The operator-facing value here is not just "pass/fail". It is being able
    # to see which exact expectation broke:
    # - canonical row missing
    # - provenance row missing
    # - link row missing
    # - skill count mismatch
    #
    # That makes the report useful for both manual inspection and later
    # automation of bulk-ingest safety gates.
    checks: list[PersistenceVerificationCheck] = [
        PersistenceVerificationCheck(
            name="candidate_profile_exists",
            passed=candidate_profile is not None,
            details=(
                "Candidate profile row was found for the expected candidate ID."
                if candidate_profile is not None
                else "No canonical candidate profile row was found."
            ),
        ),
        PersistenceVerificationCheck(
            name="candidate_profile_person_matches",
            passed=(
                candidate_profile is not None
                and candidate_profile.get("person_id") == expected["person_id"]
            ),
            details=(
                "Candidate profile points at the expected person row."
                if candidate_profile is not None
                and candidate_profile.get("person_id") == expected["person_id"]
                else "Candidate profile did not point at the expected person row."
            ),
        ),
        PersistenceVerificationCheck(
            name="candidate_source_record_exists",
            passed=_source_record_exists(
                source_records,
                expected["candidate_source_record_id"],
            ),
            details=(
                "Candidate source-record row was found."
                if _source_record_exists(
                    source_records,
                    expected["candidate_source_record_id"],
                )
                else "Candidate source-record row was missing."
            ),
        ),
        PersistenceVerificationCheck(
            name="extraction_source_record_exists",
            passed=_source_record_exists(
                source_records,
                expected["extraction_source_record_id"],
            ),
            details=(
                "Extraction source-record row was found."
                if _source_record_exists(
                    source_records,
                    expected["extraction_source_record_id"],
                )
                else "Extraction source-record row was missing."
            ),
        ),
        PersistenceVerificationCheck(
            name="candidate_source_links_candidate",
            passed=_has_source_link(
                source_record_links,
                source_record_id=expected["candidate_source_record_id"],
                candidate_id=expected["candidate_id"],
            ),
            details=(
                "Candidate source record links to the expected candidate row."
                if _has_source_link(
                    source_record_links,
                    source_record_id=expected["candidate_source_record_id"],
                    candidate_id=expected["candidate_id"],
                )
                else "Candidate source record did not link to the expected candidate row."
            ),
        ),
        PersistenceVerificationCheck(
            name="candidate_source_links_person",
            passed=_has_source_link(
                source_record_links,
                source_record_id=expected["candidate_source_record_id"],
                person_id=expected["person_id"],
            ),
            details=(
                "Candidate source record links to the expected person row."
                if _has_source_link(
                    source_record_links,
                    source_record_id=expected["candidate_source_record_id"],
                    person_id=expected["person_id"],
                )
                else "Candidate source record did not link to the expected person row."
            ),
        ),
        PersistenceVerificationCheck(
            name="extraction_source_links_candidate",
            passed=_has_source_link(
                source_record_links,
                source_record_id=expected["extraction_source_record_id"],
                candidate_id=expected["candidate_id"],
            ),
            details=(
                "Extraction source record links to the expected candidate row."
                if _has_source_link(
                    source_record_links,
                    source_record_id=expected["extraction_source_record_id"],
                    candidate_id=expected["candidate_id"],
                )
                else "Extraction source record did not link to the expected candidate row."
            ),
        ),
        PersistenceVerificationCheck(
            name="extraction_source_links_person",
            passed=_has_source_link(
                source_record_links,
                source_record_id=expected["extraction_source_record_id"],
                person_id=expected["person_id"],
            ),
            details=(
                "Extraction source record links to the expected person row."
                if _has_source_link(
                    source_record_links,
                    source_record_id=expected["extraction_source_record_id"],
                    person_id=expected["person_id"],
                )
                else "Extraction source record did not link to the expected person row."
            ),
        ),
    ]

    expected_company_id = expected.get("current_company_id")
    if expected_company_id is not None:
        checks.extend(
            [
                PersistenceVerificationCheck(
                    name="current_company_exists",
                    passed=current_company is not None,
                    details=(
                        "Expected current company row was found."
                        if current_company is not None
                        else "Expected current company row was missing."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="extraction_source_links_company",
                    passed=_has_source_link(
                        source_record_links,
                        source_record_id=expected["extraction_source_record_id"],
                        company_id=expected_company_id,
                    ),
                    details=(
                        "Extraction source record links to the expected company row."
                        if _has_source_link(
                            source_record_links,
                            source_record_id=expected["extraction_source_record_id"],
                            company_id=expected_company_id,
                        )
                        else "Extraction source record did not link to the expected company row."
                    ),
                ),
            ]
        )

    expected_document_id = expected.get("document_id")
    if expected_document_id is not None:
        checks.extend(
            [
                PersistenceVerificationCheck(
                    name="resume_document_exists",
                    passed=resume_document is not None,
                    details=(
                        "Expected resume document row was found."
                        if resume_document is not None
                        else "Expected resume document row was missing."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="resume_source_record_exists",
                    passed=_source_record_exists(
                        source_records,
                        expected.get("resume_source_record_id"),
                    ),
                    details=(
                        "Resume source-record row was found."
                        if _source_record_exists(
                            source_records,
                            expected.get("resume_source_record_id"),
                        )
                        else "Resume source-record row was missing."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="document_link_candidate_exists",
                    passed=_has_document_link(
                        document_links,
                        candidate_id=expected["candidate_id"],
                    ),
                    details=(
                        "Resume document links to the expected candidate row."
                        if _has_document_link(
                            document_links,
                            candidate_id=expected["candidate_id"],
                        )
                        else "Resume document did not link to the expected candidate row."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="document_link_person_exists",
                    passed=_has_document_link(
                        document_links,
                        person_id=expected["person_id"],
                    ),
                    details=(
                        "Resume document links to the expected person row."
                        if _has_document_link(
                            document_links,
                            person_id=expected["person_id"],
                        )
                        else "Resume document did not link to the expected person row."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="extraction_source_links_document",
                    passed=_has_source_link(
                        source_record_links,
                        source_record_id=expected["extraction_source_record_id"],
                        document_id=expected_document_id,
                    ),
                    details=(
                        "Extraction source record links to the expected document row."
                        if _has_source_link(
                            source_record_links,
                            source_record_id=expected["extraction_source_record_id"],
                            document_id=expected_document_id,
                        )
                        else "Extraction source record did not link to the expected document row."
                    ),
                ),
            ]
        )

    if isinstance(expected_skill_count, int):
        checks.append(
            PersistenceVerificationCheck(
                name="candidate_skill_count_matches",
                passed=len(candidate_skills) == expected_skill_count,
                details=(
                    f"Expected {expected_skill_count} candidate-skill rows and found {len(candidate_skills)}."
                ),
            )
        )

    expected_note_interaction_count = expected.get("candidate_note_interaction_count")
    if isinstance(expected_note_interaction_count, int):
        checks.extend(
            [
                PersistenceVerificationCheck(
                    name="candidate_note_interaction_count_matches",
                    passed=(
                        len(candidate_note_interactions)
                        == expected_note_interaction_count
                    ),
                    details=(
                        "Expected "
                        f"{expected_note_interaction_count} candidate-note interactions "
                        f"and found {len(candidate_note_interactions)}."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="candidate_note_interaction_candidate_links_match",
                    passed=(
                        _count_interaction_participants(
                            interaction_participants,
                            candidate_id=expected["candidate_id"],
                        )
                        == expected_note_interaction_count
                    ),
                    details=(
                        "Expected "
                        f"{expected_note_interaction_count} candidate-linked note participants "
                        "for the persisted JobAdder notes."
                    ),
                ),
                PersistenceVerificationCheck(
                    name="candidate_note_interaction_person_links_match",
                    passed=(
                        _count_interaction_participants(
                            interaction_participants,
                            person_id=expected["person_id"],
                        )
                        == expected_note_interaction_count
                    ),
                    details=(
                        "Expected "
                        f"{expected_note_interaction_count} person-linked note participants "
                        "for the persisted JobAdder notes."
                    ),
                ),
            ]
        )

    return checks


def _source_record_exists(
    source_records: list[dict[str, Any]],
    source_record_id: str | None,
) -> bool:
    """
    Return whether the expected source-record row exists in the snapshot.

    Example
    -------
    A check such as:

        _source_record_exists(source_records, "source-uuid")

    returns `True` when one of the fetched source-record rows has that exact
    ID, otherwise `False`.
    """

    if source_record_id is None:
        return False
    return any(row.get("id") == source_record_id for row in source_records)


def _has_source_link(
    source_record_links: list[dict[str, Any]],
    *,
    source_record_id: str,
    person_id: str | None = None,
    candidate_id: str | None = None,
    company_id: str | None = None,
    document_id: str | None = None,
) -> bool:
    """
    Return whether one exact source-record link exists in the snapshot.

    Example
    -------
    A call with:

        _has_source_link(
            source_record_links,
            source_record_id="source-uuid",
            candidate_id="candidate-uuid",
        )

    returns `True` when the verification snapshot contains that exact
    source-to-candidate link row.
    """

    for row in source_record_links:
        if row.get("source_record_id") != source_record_id:
            continue
        if person_id is not None and row.get("person_id") == person_id:
            return True
        if candidate_id is not None and row.get("candidate_id") == candidate_id:
            return True
        if company_id is not None and row.get("company_id") == company_id:
            return True
        if document_id is not None and row.get("document_id") == document_id:
            return True
    return False


def _has_document_link(
    document_links: list[dict[str, Any]],
    *,
    person_id: str | None = None,
    candidate_id: str | None = None,
) -> bool:
    """
    Return whether one exact document link exists in the snapshot.

    Example
    -------
    A call with:

        _has_document_link(
            document_links,
            person_id="person-uuid",
        )

    returns `True` when the verification snapshot contains a document link for
    that person.
    """

    for row in document_links:
        if person_id is not None and row.get("person_id") == person_id:
            return True
        if candidate_id is not None and row.get("candidate_id") == candidate_id:
            return True
    return False


def _count_interaction_participants(
    interaction_participants: list[dict[str, Any]],
    *,
    person_id: str | None = None,
    candidate_id: str | None = None,
) -> int:
    """
    Return the number of interaction-participant rows matching one entity target.

    Example
    -------
    A persisted note slice with three note interactions should usually produce
    three candidate participant rows and three person participant rows.
    """

    count = 0
    for row in interaction_participants:
        if person_id is not None and row.get("person_id") == person_id:
            count += 1
        elif candidate_id is not None and row.get("candidate_id") == candidate_id:
            count += 1
    return count


__all__ = [
    "PersistenceVerificationCheck",
    "ResumeExtractionPersistenceVerification",
    "verify_persisted_resume_extraction_result",
]
