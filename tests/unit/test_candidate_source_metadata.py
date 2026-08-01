from backend.services import candidate_source_metadata
from backend.services.candidate_source_metadata import (
    attach_candidate_source_metadata,
    classify_candidate_source_category,
)


def test_classify_candidate_source_category_distinguishes_provenance() -> None:
    assert (
        classify_candidate_source_category(
            ["linkedin_helper"],
            has_resume_document=False,
        )
        == "profile_only"
    )
    assert (
        classify_candidate_source_category(
            ["dropbox", "linkedin_helper"],
            has_resume_document=True,
        )
        == "cross_source"
    )
    assert (
        classify_candidate_source_category(
            ["dropbox"],
            has_resume_document=True,
        )
        == "cv_backed"
    )
    assert (
        classify_candidate_source_category(
            ["recruitly"],
            has_resume_document=False,
        )
        == "profile_only"
    )
    assert classify_candidate_source_category([]) == "unknown"


def test_attach_candidate_source_metadata_uses_one_batched_lookup(
    monkeypatch,
) -> None:
    captured_candidate_ids: set[str] = set()

    def fake_get_candidate_source_details(
        candidate_ids: set[str],
    ) -> dict[str, list[dict[str, str]]]:
        captured_candidate_ids.update(candidate_ids)
        return {
            "candidate-1": [
                {
                    "source_system": "dropbox",
                    "latest_record_received_at": "2026-06-10T09:00:00+00:00",
                },
                {
                    "source_system": "linkedin_helper",
                    "latest_record_received_at": "2026-07-20T14:30:00+00:00",
                },
            ],
            "candidate-2": [
                {
                    "source_system": "linkedin_helper",
                    "latest_record_received_at": "2026-07-21T14:30:00+00:00",
                }
            ],
        }

    monkeypatch.setattr(
        candidate_source_metadata,
        "get_candidate_source_details",
        fake_get_candidate_source_details,
    )

    results = attach_candidate_source_metadata(
        [
            {
                "candidate_id": "candidate-1",
                "full_name": "Cross Source",
                "document_id": "document-1",
            },
            {
                "candidate_id": "candidate-2",
                "full_name": "Profile Only",
                "document_id": None,
            },
        ]
    )

    assert captured_candidate_ids == {"candidate-1", "candidate-2"}
    assert results[0]["source_systems"] == ["dropbox", "linkedin_helper"]
    assert results[0]["source_details"][1] == {
        "source_system": "linkedin_helper",
        "latest_record_received_at": "2026-07-20T14:30:00+00:00",
    }
    assert results[0]["source_category"] == "cross_source"
    assert results[1]["source_category"] == "profile_only"
