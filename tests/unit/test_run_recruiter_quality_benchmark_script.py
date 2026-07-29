"""
Tests for the recruiter-quality benchmark operator script.
"""

from scripts.run_recruiter_quality_benchmark import (
    _source_category,
    _summarize_results,
)


def test_source_category_distinguishes_linkedin_helper_provenance() -> None:
    assert _source_category(["linkedin_helper"]) == "linkedin_helper_only"
    assert (
        _source_category(["dropbox", "linkedin_helper", "recruiterflow"])
        == "cross_source"
    )
    assert _source_category(["dropbox"]) == "other_source"
    assert _source_category([]) == "unknown"


def test_summarize_results_aggregates_quality_and_source_metrics() -> None:
    results = [
        {
            "retrieval": [{}, {}],
            "shortlist": [{}],
            "linkedin_helper_only_retrieval_count": 1,
            "linkedin_helper_only_shortlist_count": 0,
            "cross_source_retrieval_count": 1,
            "cross_source_shortlist_count": 1,
            "previous_shortlist_overlap_count": 1,
            "previous_shortlist_retrieval_count": 2,
        },
        {
            "retrieval": [{}],
            "shortlist": [{}, {}],
            "linkedin_helper_only_retrieval_count": 0,
            "linkedin_helper_only_shortlist_count": 0,
            "cross_source_retrieval_count": 0,
            "cross_source_shortlist_count": 0,
            "previous_shortlist_overlap_count": 0,
            "previous_shortlist_retrieval_count": 1,
        },
    ]

    assert _summarize_results(results) == {
        "roles": 2,
        "retrieved_candidates": 3,
        "shortlisted_candidates": 3,
        "linkedin_helper_only_retrieval": 1,
        "linkedin_helper_only_shortlist": 0,
        "cross_source_retrieval": 1,
        "cross_source_shortlist": 1,
        "previous_shortlist_overlap": 1,
        "previous_shortlist_retrieval_hits": 3,
    }
