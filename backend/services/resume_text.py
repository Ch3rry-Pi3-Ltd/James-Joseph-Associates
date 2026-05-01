"""
Resume text-extraction helpers.

This module is the next stage after transient CV download.

Why this module exists
----------------------
By this point in the JobAdder pipeline, the backend can already:

- fetch candidate detail
- fetch candidate attachments
- identify the latest likely resume
- download the selected attachment bytes

The next problem is different:

    "Can the backend turn raw resume file bytes into usable plain text?"

That is what this module is for.

Why text extraction matters
---------------------------
Later stages such as:

- LLM-based skills extraction
- current-employer extraction
- education parsing
- employment-history parsing
- canonical profile enrichment

all need text, not just raw PDF bytes.

So this module creates the boundary between:

- binary document retrieval, and
- downstream semantic understanding

Scope of this first version
---------------------------
This module intentionally starts narrow.

It does:

- validate that resume bytes exist
- parse PDF bytes with `pypdf`
- extract page text
- normalise that text into one combined string
- return a small metadata wrapper

It does not:

- store the PDF
- OCR scanned/image-only PDFs
- run an LLM
- infer skills or employers
- write to the database
- handle Word documents yet

That narrow scope is deliberate. The first goal is simply to prove that the
downloaded resume bytes can be turned into usable text reliably.

Example
-------
A typical caller later in the pipeline might do:

    extracted_resume = extract_text_from_pdf_bytes(
        content_bytes=downloaded_resume["content_bytes"],
        file_name=downloaded_resume.get("file_name"),
    )

and receive a result shaped like:

    {
        "text": "...full extracted text...",
        "page_count": 3,
        "extractor": "pypdf",
        "file_name": "Roger Campbell - CV 2025.pdf",
        "character_count": 8421,
    }

In plain language:

- give this module PDF bytes
- get back plain text plus a little extraction metadata
- hand that text to later parsing or LLM stages
"""

from io import BytesIO
from typing import Any

try:
    from pypdf import PdfReader

except ImportError as exc:  # pagma: no cover - handled at runtime, not by logic
    raise RuntimeError(
        "The `pypdf` package is required for resume text extraction. "
        "Add `pypdf` to the project dependencies before using this module."
    ) from exc

class ResumeTextExtractionError(RuntimeError):
    """
    Raised when the backend cannot extract usable text from a resume document.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    stage : str
        Small machine-readable label describing where extraction failed.

        Common values in this module include:

        - `input_validation`
        - `pdf_parse`
        - `text_extraction`
        - `text_normalisation`

    details : list[dict[str, Any]]
        Small structured metadata that helps explain the failure without
        carrying the raw document bytes.

    Example
    -------
    A caller may catch this exception and inspect:

        error.stage
        error.details

    to distinguish between:

    - empty input bytes
    - unreadable PDF structure
    - extraction that technically ran but produced no usable text
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or []

    def __str__(self) -> str:
        """
        Return the human-readable error message only.

        Example
        -------
        Calling:

            str(error)

        returns just the main explanation, while richer context remains on:

        - `error.stage`
        - `error.details`

        In plain language:

        - print the main message
        - keep the structured debugging context on the object itself
        """

        return self.message
    
def extract_text_from_pdf_bytes(
    *,
     content_bytes: bytes,
     file_name: str | None = None,
) -> dict[str, Any]:
    """
    Extract plain text from PDF resume bytes.

    Parameters
    ----------
    content_bytes : bytes
        Raw PDF bytes, typically returned from a transient attachment-download
        step such as the JobAdder resume-download helper.

    file_name : str | None
        Optional source file name used only for metadata and clearer error
        reporting.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `text`
        - `page_count`
        - `extractor`
        - `file_name`
        - `character_count`

    Raises
    ------
    ResumeTextExtractionError
        If the input bytes empty, the PDF cannot be parsed, or no usable
        text can be extracted.

    Example
    -------
    A typical call looks like:

        extract_text_from_pdf_bytes(
            content_bytes=downloaded_resume["content_bytes"],
            file_name=downloaded_resume.get("file_name"),
        )
    
    and a successful result looks like:

        {
            "text": "Roger Campbell\\nSenior ...",
            "page_count": 2,
            "extractor": "pypdf",
            "file_name": "Roger Campbell - CV 2025.pdf",
            "character_count": 5120,
        }

    Notes
    -----
    - This helper is intentionally PDF-specific.
    - It does not try to infer document type from magic bytes yet.
    - It assumes the caller already decided that the downloaded attachment is
      the document it wants to parse.
    - If later you need DOCX or OCR support, add separate helpers rather than
      overloading this one into a vague "extract anything" function.

    In plain language:

    - check the bytes are present
    - parse the PDF safely
    - extract text page by page
    - normalise that text into one combined string
    - return the text with small extraction metadata
    """

    # Fail early on obviously unusable input
    #   - This keeps the function honest about what it needs:
    #     real document bytes.
    #   - It also keeps downstream failures clearer. An empty-byte error should be
    #     reported as an input problem, not as a mysterious "PDF parsing failed"
    #     problem two layers later.
    if not isinstance(content_bytes, bytes):
        raise ResumeTextExtractionError(
            "Resume content must be provided as raw bytes.",
            stage="input_validation",
            details=[{"file_name": file_name}],
        )
    
    if len(content_bytes) == 0:
        raise ResumeTextExtractionError(
            "Resume content bytes are empty.",
            stage="input_validation",
            details=[{"file_name": file_name}],
        )
    
    # Parse from an in-memory stream rather than writing a temporary file
    #   - That matters for both simplicity and cost:
    #
    #       - no filesystem churn
    #       - no temp-file cleanup burden
    #       - easier later use inside API handlers or background jobs
    #   
    #   - It also matches the current transient-document stragegy, where the PDF
    #     is downloaded, processed, and then allowed to disappear unless later
    #     product requirements say otherwise.
    try:
        reader = PdfReader(BytesIO(content_bytes))
    except Exception as exc:
        raise ResumeTextExtractionError(
            "The resume PDF could not be parsed.",
            stage="pdf_parse",
            details=[{"file_name": file_name}],
        ) from exc
    
    pages = reader.pages
    page_count = len(pages)

    # A PDF with zero pages is technically a parsed PDF object, but it is still
    # unusable for resume extraction
    #   - Surfacing this explicitly is better than returning empty text and forcing
    #     later stages to guess whether the CV was blank, broken, or simply missing.
    if page_count == 0:
        raise ResumeTextExtractionError(
            "The resume PDF does not contain any pages.",
            stage="pdf_parse",
            details=[{"file_name": file_name}],
        )
    
    extracted_page_texts: list[str] = []

    # Extract text page by page rather than trying to flatten everything in one
    # opaque operation
    #   - This is the more explainable design:
    #
    #       - page-level extraction failures are easier to reason about
    #       - later enhancements can preserve page boundaries if needed
    #       - the code stays open to future metadata such as per-page text lengths
    #
    #   - Even though the first version only returns one combined string, keeping
    #     page-wise processing here is the right foundation.
    for page_index, page in enumerate(pages, start=1):
        try:
            raw_page_text = page.extract_text()
        except Exception as exc:
            raise ResumeTextExtractionError(
                "Text extraction failed for one of the PDF pages.",
                stage="text_extraction",
                details=[
                    {"file_name": file_name},
                    {"page_number": page_index},
                ],
            ) from exc

        # Normalise each page immediately so that the final combined output is
        # less noisy and more stable for downstream prompt inputs.
        #   - Resume PDFs often contain inconsistent whitespace:
        #
        #       - double newlines
        #       - trailing spaces
        #       - empty lines from layout artifacts
        #
        #   - Cleaning per page keeps that mess from compounding when the pages are
        #     joined together later.
        normalised_page_text = _normalise_extracted_page_text(raw_page_text)

        if normalised_page_text != "":
            extracted_page_texts.append(normalised_page_text)

    # It is possible for a PDF to parse successfully but still yield no usable text
    #   - Common causes include:
    #
    #       - image-only scanned CVs
    #       - highly unusual PDF structure
    #       - extraction limitations in the underlying parser
    #
    #   - This is not the same thing as successful extraction, so fail clearly.
    if len(extracted_page_texts) == 0:
        raise ResumeTextExtractionError(
            "The resume PDF did not yield any usable text.",
            stage="text_extraction",
            details=[
                {"file_name": file_name},
                {"page_count": page_count},
            ]
        )
    
    # Join pages with a double newline so the later text still carries some
    # structural hint that page boundaries existed
    #   - That is a small but useful compromise:
    #
    #       - one plain string is easy to store and pass to an LLM
    #       - double newlines preserve a little document rhythm
    #       - we avoid over-engineering page segmentation in the first version
    combined_text = "\n\n".join(extracted_page_texts).strip()

    if combined_text == "":
        raise ResumeTextExtractionError(
            "The extracted resume text became empty after normalisation.",
            stage="text_normalisation",
            details=[
                {"file_name": file_name},
                {"page_count": page_count},
            ],
        )
    
    return {
        "text": combined_text,
        "page_count": page_count,
        "extractor": "pypdf",
        "file_name": file_name,
        "character_count": len(combined_text)
    }

def _normalise_extracted_page_text(raw_page_text: Any) -> str:
    """
    Normalise one extracted PDF page into cleaner plain text.

    Parameters
    ----------
    raw_page_text : Any
        Raw page text returned by the PDF parser.

    Returns
    -------
    str
        Cleaned plain text for one page, or an empty string when the page did
        not produce usable text.

    Example
    -------
    A raw extracted page like:

        "Roger Campbell\\n\\nSenior Data Scientist  \\n\\n"

    becomes something closer to:

        "Roger Campbell\\nSenior Data Scientist"

    Notes
    -----
    - This helper is intentionally conservative.
    - It removes obvious whitespace but does not attempt semantic
      rewriting.
    - The goal is to make later extraction more stable, not to "improve" the
      candidate's wording.
    """

    if not isinstance(raw_page_text, str):
        return ""
    
    # Trim each line individually first
    #   - This helps with the common PDF-extraction pattern where the text itself is
    #     usable, but each line arrives padded with layout whitespace.
    raw_lines = raw_page_text.splitlines()
    stripped_lines = [line.strip() for line in raw_lines]

    cleaned_lines: list[str] = []
    previous_line_blank = False

    # Collapse repeated blank lines while preserving single blank-line breaks
    #   - That gives later LLM or rule-based extraction some natural separation
    #     between sections such as:
    #
    #       - summary
    #       - experience
    #       - education
    #
    #     without leaving the output full of extraction noise.
    for line in stripped_lines:
        is_blank = line == ""

        if is_blank:
            if not previous_line_blank and len(cleaned_lines) > 0:
                cleaned_lines.append("")
            previous_line_blank = True
            continue

        cleaned_lines.append(line)
        previous_line_blank = False

    normalised_text = "\n".join(cleaned_lines).strip()

    return normalised_text

__all__ = [
    "ResumeTextExtractionError",
    "extract_text_from_pdf_bytes",
]
