from backend.services.document_chunking import (
    chunk_document_text,
    estimate_token_count,
    normalize_chunk_source_text,
)


def test_normalize_chunk_source_text_compacts_whitespace() -> None:
    raw_text = "  Senior   data engineer \n\n Python\tSQL   AWS  \n"

    result = normalize_chunk_source_text(raw_text)

    assert result == "Senior data engineer\nPython SQL AWS"


def test_estimate_token_count_uses_whitespace_words() -> None:
    assert estimate_token_count("Python SQL AWS") == 3
    assert estimate_token_count("   ") == 0


def test_chunk_document_text_splits_large_text_into_multiple_chunks() -> None:
    text = (
        "Senior Data Engineer with Python and SQL experience. "
        "Built AWS ETL pipelines for analytics teams. "
        "Worked closely with stakeholders in regulated environments. "
        "Led production data platform improvements and reporting workflows."
    )

    chunks = chunk_document_text(
        text,
        max_chars=80,
        overlap_chars=10,
    )

    assert len(chunks) >= 2
    assert all(chunk.strip() != "" for chunk in chunks)
    assert any("Python" in chunk for chunk in chunks)
    assert any("regulated environments" in chunk for chunk in chunks)


def test_chunk_document_text_rejects_invalid_overlap() -> None:
    try:
        chunk_document_text("hello world", max_chars=10, overlap_chars=10)
    except ValueError as error:
        assert "smaller than max_chars" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for invalid overlap.")
