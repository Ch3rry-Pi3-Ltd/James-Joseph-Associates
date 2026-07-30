from backend.services import candidate_source_metadata
from backend.services.candidate_source_metadata import (
    attach_candidate_source_metadata,
    classify_candidate_source_category,
)


def test_classify_candidate_source_category_distinguishes_provenance() -> None:
    assert (
        classify_candidate_source_category(["linkedin_helper"])
        == "linkedin_helper_only"
    )
    assert (
        classify_candidate_source_category(["dropbox", "linkedin_helper"])
        == "cross_source"
    )
    assert classify_candidate_source_category(["dropbox"]) == "cv_backed"
    assert classify_candidate_source_category([]) == "unknown"


def test_attach_candidate_source_metadata_uses_one_batched_lookup(
    monkeypatch,
) -> None:
    captured_candidate_ids: set[str] = set()

    def fake_get_candidate_source_systems(
        candidate_ids: set[str],
    ) -> dict[str, list[str]]:
        captured_candidate_ids.update(candidate_ids)
        return {
            "candidate-1": ["dropbox", "linkedin_helper"],
            "candidate-2": ["linkedin_helper"],
        }

    monkeypatch.setattr(
        candidate_source_metadata,
        "get_candidate_source_systems",
        fake_get_candidate_source_systems,
    )

    results = attach_candidate_source_metadata(
        [
            {"candidate_id": "candidate-1", "full_name": "Cross Source"},
            {"candidate_id": "candidate-2", "full_name": "Profile Only"},
        ]
    )

    assert captured_candidate_ids == {"candidate-1", "candidate-2"}
    assert results[0]["source_category"] == "cross_source"
    assert results[1]["source_category"] == "linkedin_helper_only"
