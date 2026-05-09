"""
Unit tests for resume text-extraction helpers.

This module tests the document-to-text boundary in
`backend.services.resume_text`.

Why these tests matter
----------------------
By this point in the broader ingestion flow, the backend can already:

- identify the latest likely JobAdder resume
- download the selected attachment bytes transiently

The next question is different:

    "Can the backend turn those raw resume-document bytes into usable plain
    text?"

That matters because every later enrichment step depends on text rather than
binary file content.

These tests therefore protect the first document-understanding boundary:

- valid PDF bytes should extract into plain text
- valid DOCX bytes should extract into plain text
- bad input should fail clearly
- parse failures should be distinguished from no-text failures
- whitespace clean-up should stay predictable for later LLM input

Scope of these tests
--------------------
These tests intentionally do not:

- call any external APIs
- download any real CVs
- run an LLM
- write to the database

Instead, they focus on the local behaviour of:

- `extract_text_from_resume_bytes(...)`
- `extract_text_from_docx_bytes(...)`
- `extract_text_from_pdf_bytes(...)`
- `_normalise_extracted_page_text(...)`

Example
-------
A typical happy-path test in this module:

- creates a tiny in-memory PDF
- patches one page to return known text
- confirms the helper returns:
  - combined text
  - page count
  - extractor name
  - character count

In plain language:

- give the module fake PDF bytes
- confirm it returns clean, usable text
- confirm failures are classified clearly when the bytes are bad
"""

from io import BytesIO
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter

import backend.services.resume_text as resume_text
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_docx_bytes,
    extract_text_from_pdf_bytes,
    extract_text_from_resume_bytes,
)


def _build_minimal_pdf_bytes(page_count: int = 1) -> bytes:
    """
    Build a tiny in-memory PDF for tests.

    Parameters
    ----------
    page_count : int
        Number of blank pages to include in the generated PDF.

    Returns
    -------
    bytes
        Valid PDF bytes that `pypdf.PdfReader` can parse.

    Notes
    -----
    - The generated pages are blank by default.
    - That is fine for these tests because the text extraction itself is often
      patched or controlled separately.
    - Using a real parseable PDF keeps the tests grounded in the same library
      behaviour the production helper relies on.
    """

    writer = PdfWriter()

    for _ in range(page_count):
        writer.add_blank_page(width=300, height=300)

    stream = BytesIO()
    writer.write(stream)

    return stream.getvalue()


def _build_minimal_docx_bytes(*paragraphs: str) -> bytes:
    """
    Build a tiny in-memory DOCX-like ZIP payload for tests.

    Parameters
    ----------
    *paragraphs : str
        Paragraph strings to place inside `word/document.xml`.

    Returns
    -------
    bytes
        ZIP bytes containing the minimal XML our DOCX helper relies on.

    Notes
    -----
    - The production parser intentionally reads only `word/document.xml`.
    - The test helper mirrors that narrow contract instead of trying to build a
      fully standards-complete Word file.
    - That keeps the tests focused on our local extraction logic.
    """

    paragraph_xml = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraph_xml}</w:body>"
        "</w:document>"
    )

    stream = BytesIO()

    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    return stream.getvalue()


def test_extract_text_from_pdf_bytes_returns_text_metadata_for_valid_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a valid PDF produces clean extracted text and metadata.

    Notes
    -----
    - We still use real parseable PDF bytes here.
    - We patch `PageObject.extract_text` so the test can control the exact text
      returned without depending on PDF text-layout quirks.
    - That keeps the test focused on our helper's orchestration and
      normalisation logic rather than on the internals of PDF text encoding.

    Example
    -------
    We simulate a two-page PDF where the parser returns:

    - page 1: `"Roger Campbell\\n\\nSenior Data Scientist"`
    - page 2: `"Python\\nMachine Learning"`

    and confirm the helper returns one combined string with:

    - double-newline page separation
    - correct page count
    - correct extractor name
    - correct character count

    In plain language:

    - pretend a PDF has two pages of useful text
    - confirm the helper returns one clean text bundle
    """

    pdf_bytes = _build_minimal_pdf_bytes(page_count=2)
    page_texts = iter(
        [
            "Roger Campbell\n\nSenior Data Scientist",
            "Python\nMachine Learning",
        ]
    )

    def fake_extract_text(self):
        return next(page_texts)

    monkeypatch.setattr(
        "pypdf._page.PageObject.extract_text",
        fake_extract_text,
    )

    result = extract_text_from_pdf_bytes(
        content_bytes=pdf_bytes,
        file_name="Roger Campbell - CV 2025.pdf",
    )

    expected_text = (
        "Roger Campbell\n\nSenior Data Scientist\n\nPython\nMachine Learning"
    )

    assert result == {
        "text": expected_text,
        "page_count": 2,
        "extractor": "pypdf",
        "file_name": "Roger Campbell - CV 2025.pdf",
        "character_count": len(expected_text),
    }


def test_extract_text_from_docx_bytes_returns_text_metadata_for_valid_docx() -> None:
    """
    Verify that a valid DOCX payload produces clean extracted text and
    metadata.

    Notes
    -----
    - This test uses a tiny in-memory ZIP rather than a fixture file.
    - That keeps the test fast and makes the expected XML structure explicit.
    - The goal is to pin our own paragraph reconstruction and metadata shape,
      not to exercise every possible Word-processing feature.
    """

    docx_bytes = _build_minimal_docx_bytes(
        "Isaiah Perumalla",
        "Senior Data Engineer",
        "Python Azure Databricks",
    )

    expected_text = (
        "Isaiah Perumalla\n\nSenior Data Engineer\n\nPython Azure Databricks"
    )

    result = extract_text_from_docx_bytes(
        content_bytes=docx_bytes,
        file_name="Isaiah Perumalla.docx",
    )

    assert result == {
        "text": expected_text,
        "page_count": None,
        "extractor": "docx_xml",
        "file_name": "Isaiah Perumalla.docx",
        "character_count": len(expected_text),
    }


def test_extract_text_from_resume_bytes_dispatches_to_docx_parser() -> None:
    """
    Verify that the format-dispatch helper routes DOCX files to the DOCX
    parser.

    Notes
    -----
    - This protects the new orchestration boundary that the JobAdder ingest
      helper now depends on.
    - A DOCX attachment should not fall through to the PDF parser simply
      because the bytes happen to be a ZIP container.
    """

    docx_bytes = _build_minimal_docx_bytes("Susmitha Valluru", "Data Engineer")

    result = extract_text_from_resume_bytes(
        content_bytes=docx_bytes,
        file_name="Susmitha-Valluru_cv-library.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result["extractor"] == "docx_xml"
    assert result["page_count"] is None
    assert result["text"] == "Susmitha Valluru\n\nData Engineer"


def test_extract_text_from_pdf_bytes_raises_when_input_is_not_bytes() -> None:
    """
    Verify that the helper rejects non-byte input immediately.

    Notes
    -----
    - This is local caller-input validation.
    - The helper should fail before it attempts any PDF parsing at all.

    In plain language:

    - pass the wrong Python type
    - confirm the helper raises a clear input-validation error
    """

    with pytest.raises(ResumeTextExtractionError) as exc_info:
        extract_text_from_pdf_bytes(
            content_bytes="not-bytes",  # type: ignore[arg-type]
            file_name="bad-input.pdf",
        )

    error = exc_info.value

    assert str(error) == "Resume content must be provided as raw bytes."
    assert error.stage == "input_validation"
    assert error.details == [{"file_name": "bad-input.pdf"}]


def test_extract_text_from_pdf_bytes_raises_when_bytes_are_empty() -> None:
    """
    Verify that empty PDF bytes are rejected as an input problem.

    Notes
    -----
    - This should not be reported as a parse failure.
    - The helper should classify it as bad input instead.

    In plain language:

    - pass empty bytes
    - confirm the helper raises an input-validation error
    """

    with pytest.raises(ResumeTextExtractionError) as exc_info:
        extract_text_from_pdf_bytes(
            content_bytes=b"",
            file_name="empty.pdf",
        )

    error = exc_info.value

    assert str(error) == "Resume content bytes are empty."
    assert error.stage == "input_validation"
    assert error.details == [{"file_name": "empty.pdf"}]


def test_extract_text_from_pdf_bytes_raises_when_pdf_cannot_be_parsed() -> None:
    """
    Verify that unreadable PDF bytes become a parse-stage error.

    Notes
    -----
    - This covers the case where the backend has bytes, but they are not a
      parseable PDF document.
    - That is different from the empty-bytes case because the caller did pass
      content, just not content the parser can understand.

    In plain language:

    - pass corrupt or non-PDF bytes
    - confirm the helper raises a parse error
    """

    with pytest.raises(ResumeTextExtractionError) as exc_info:
        extract_text_from_pdf_bytes(
            content_bytes=b"this is not a real pdf",
            file_name="corrupt.pdf",
        )

    error = exc_info.value

    assert str(error) == "The resume PDF could not be parsed."
    assert error.stage == "pdf_parse"
    assert error.details == [{"file_name": "corrupt.pdf"}]


def test_extract_text_from_docx_bytes_raises_when_docx_cannot_be_parsed() -> None:
    """
    Verify that unreadable DOCX bytes become a DOCX-parse-stage error.

    Notes
    -----
    - DOCX files are ZIP containers, so random bytes should fail before any XML
      parsing or text extraction logic runs.
    - Keeping this distinct from `text_extraction` matters because it tells the
      ingest layer whether the file itself was structurally unreadable.
    """

    with pytest.raises(ResumeTextExtractionError) as exc_info:
        extract_text_from_docx_bytes(
            content_bytes=b"not really a docx file",
            file_name="broken.docx",
        )

    error = exc_info.value

    assert str(error) == "The resume DOCX could not be parsed."
    assert error.stage == "docx_parse"
    assert error.details == [{"file_name": "broken.docx"}]


def test_extract_text_from_pdf_bytes_raises_when_pdf_yields_no_usable_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a parseable PDF which yields no usable text is classified
    separately from parse failure.

    Notes
    -----
    - This is an important real-world case.
    - Many CV PDFs are image-only scans or produce effectively empty output
      through basic PDF text extraction.
    - The helper should not pretend extraction succeeded just because parsing
      succeeded.

    Example
    -------
    We simulate a valid one-page PDF whose page extraction returns only blank
    whitespace. The helper should raise:

    - `ResumeTextExtractionError`
    - `stage == "text_extraction"`

    In plain language:

    - pretend the PDF parsed
    - but no usable text came out
    - confirm the helper raises the right later-stage error
    """

    pdf_bytes = _build_minimal_pdf_bytes(page_count=1)

    def fake_extract_text(self):
        return "   \n\n   "

    monkeypatch.setattr(
        "pypdf._page.PageObject.extract_text",
        fake_extract_text,
    )

    with pytest.raises(ResumeTextExtractionError) as exc_info:
        extract_text_from_pdf_bytes(
            content_bytes=pdf_bytes,
            file_name="image-only-scan.pdf",
        )

    error = exc_info.value

    assert str(error) == "The resume PDF did not yield any usable text."
    assert error.stage == "text_extraction"
    assert error.details == [
        {"file_name": "image-only-scan.pdf"},
        {"page_count": 1},
    ]


def test_normalise_extracted_page_text_collapses_whitespace_noise() -> None:
    """
    Verify that the page-normalisation helper trims lines and collapses
    repeated blank lines predictably.

    Notes
    -----
    - This is the small cleanup rule that later LLM prompts will depend on.
    - The goal is not stylistic rewriting.
    - The goal is to remove obvious extraction noise while preserving section
      breaks where they are useful.

    Example
    -------
    A raw page like:

        " Roger Campbell  \\n\\n\\n Senior Data Scientist \\n\\n Python "

    should become:

        "Roger Campbell\\n\\nSenior Data Scientist\\n\\nPython"

    In plain language:

    - feed in messy page text
    - confirm the helper returns a cleaner but structurally similar version
    """

    raw_page_text = " Roger Campbell  \n\n\n Senior Data Scientist \n\n Python "

    result = resume_text._normalise_extracted_page_text(raw_page_text)

    assert result == "Roger Campbell\n\nSenior Data Scientist\n\nPython"
