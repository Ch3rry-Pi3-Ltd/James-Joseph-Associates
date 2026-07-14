from scripts.run_recruitly_bulk_ingest import (
    _extract_recruitly_record_id,
    _should_stop_paging,
)


def test_extract_recruitly_record_id_prefers_trimmed_string() -> None:
    assert _extract_recruitly_record_id({"id": "  abc-123  "}) == "abc-123"


def test_extract_recruitly_record_id_coerces_non_string_values() -> None:
    assert _extract_recruitly_record_id({"id": 42}) == "42"


def test_extract_recruitly_record_id_returns_none_when_missing() -> None:
    assert _extract_recruitly_record_id({}) is None


def test_should_stop_paging_stops_on_empty_page() -> None:
    assert _should_stop_paging(item_count=0, total_count=None, page=0, size=100) is True


def test_should_stop_paging_stops_on_short_page() -> None:
    assert _should_stop_paging(item_count=37, total_count=None, page=0, size=100) is True


def test_should_stop_paging_stops_when_total_count_boundary_is_reached() -> None:
    assert _should_stop_paging(item_count=100, total_count=200, page=1, size=100) is True


def test_should_stop_paging_continues_when_page_is_full_and_total_is_unknown() -> None:
    assert _should_stop_paging(item_count=100, total_count=None, page=0, size=100) is False
