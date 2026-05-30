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

all need text, not just raw document bytes.

So this module creates the boundary between:

- binary document retrieval, and
- downstream semantic understanding

Scope of the current version
----------------------------
This module intentionally stays focused on local document parsing.

It does:

- validate that resume bytes exist
- parse PDF bytes with `pypdf`
- parse DOCX bytes with the standard-library ZIP/XML readers
- extract document text
- normalise that text into one combined string
- return a small metadata wrapper

It does not:

- store the original file
- OCR scanned/image-only PDFs
- run an LLM
- infer skills or employers
- write to the database
- support OCR for scanned/image-only PDFs

That narrow scope is deliberate. The goal is simply to prove that the
downloaded resume bytes can be turned into usable text reliably before the
first structured extraction stage.

Example
-------
A typical caller later in the pipeline might do:

    extracted_resume = extract_text_from_resume_bytes(
        content_bytes=downloaded_resume["content_bytes"],
        file_name=downloaded_resume.get("file_name"),
        content_type=downloaded_resume.get("content_type"),
    )

and receive a result shaped like:

    {
        "text": "...full extracted text...",
        "page_count": 3,
        "extractor": "pypdf",
        "file_name": "Roger Campbell - CV 2025.pdf",
        "character_count": 8421,
    }

or for DOCX:

    {
        "text": "...full extracted text...",
        "page_count": None,
        "extractor": "docx_xml",
        "file_name": "Isaiah Perumalla.docx",
        "character_count": 7031,
    }

In plain language:

- give this module resume bytes
- let it choose the right local parser
- get back plain text plus a little extraction metadata
- hand that text to later parsing or LLM stages
"""

from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - handled at runtime, not by logic
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
        - `docx_parse`
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

    Notes
    -----
    - This exception is for backend control flow.
    - It deliberately avoids carrying raw PDF bytes.
    - Later route handlers or background jobs can convert it into the
      project's standard error-reporting shape.
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


def extract_text_from_resume_bytes(
    *,
    content_bytes: bytes,
    file_name: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """
    Extract plain text from one supported resume document.

    Parameters
    ----------
    content_bytes : bytes
        Raw document bytes returned from a transient attachment download.

    file_name : str | None
        Optional source file name used for parser selection and clearer error
        reporting.

    content_type : str | None
        Optional MIME type returned by the upstream provider.

    Returns
    -------
    dict[str, Any]
        Normalised text-extraction metadata produced by the selected parser.

    Raises
    ------
    ResumeTextExtractionError
        If the file format is unsupported or the selected parser cannot turn
        the bytes into usable text.

    Example
    -------
    A typical orchestration-layer call looks like:

        extract_text_from_resume_bytes(
            content_bytes=downloaded_resume["content_bytes"],
            file_name=downloaded_resume.get("file_name"),
            content_type=downloaded_resume.get("content_type"),
        )

    Notes
    -----
    - This helper is intentionally a small dispatcher, not a kitchen-sink
      parser.
    - It currently supports:
        - PDF
        - DOCX
        - DOC via a local `antiword` binary when available
    - Unsupported file types fail explicitly so the ingest layer can decide
      whether that is a terminal source-data problem or a feature gap.

    In plain language:

    - inspect the file metadata
    - choose the right parser
    - return one consistent text bundle
    """

    # Derive the file type from explicit MIME type first, then fall back to the
    # file extension.
    #
    # That ordering is deliberate:
    # - provider MIME types are usually the strongest signal when present
    # - file names are still useful because some upstream systems omit or blur
    #   content types
    # - the dispatcher should stay deterministic rather than guessing from raw
    #   magic bytes unless we explicitly decide to add that later
    normalised_content_type = (
        content_type.strip().lower() if isinstance(content_type, str) else ""
    )
    normalised_file_name = file_name.strip().lower() if isinstance(file_name, str) else ""

    if normalised_content_type == "application/pdf" or normalised_file_name.endswith(
        ".pdf"
    ):
        return extract_text_from_pdf_bytes(
            content_bytes=content_bytes,
            file_name=file_name,
        )

    if (
        normalised_content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or normalised_file_name.endswith(".docx")
    ):
        return extract_text_from_docx_bytes(
            content_bytes=content_bytes,
            file_name=file_name,
        )

    if normalised_content_type == "application/msword" or normalised_file_name.endswith(
        ".doc"
    ):
        return extract_text_from_doc_bytes(
            content_bytes=content_bytes,
            file_name=file_name,
        )

    raise ResumeTextExtractionError(
        "The resume file format is not supported for text extraction.",
        stage="input_validation",
        details=[
            {"file_name": file_name},
            {"content_type": content_type},
        ],
    )


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
        If the input bytes are empty, the PDF cannot be parsed, or no usable
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

    # Fail early on obviously unusable input.
    #
    # This keeps the function honest about what it needs:
    # - real document bytes
    #
    # It also keeps downstream failures clearer. An empty-byte error should be
    # reported as an input problem, not as a mysterious "PDF parsing failed"
    # problem two layers later.
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

    # Parse from an in-memory stream rather than writing a temporary file.
    #
    # That matters for both simplicity and cost:
    # - no filesystem churn
    # - no temp-file cleanup burden
    # - easier later use inside API handlers or background jobs
    #
    # It also matches the current transient-document strategy, where the PDF is
    # downloaded, processed, and then allowed to disappear unless later
    # product requirements say otherwise.
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
    # unusable for resume extraction.
    #
    # Surfacing this explicitly is better than returning empty text and forcing
    # later stages to guess whether the CV was blank, broken, or simply
    # missing.
    if page_count == 0:
        raise ResumeTextExtractionError(
            "The resume PDF does not contain any pages.",
            stage="pdf_parse",
            details=[{"file_name": file_name}],
        )

    extracted_page_texts: list[str] = []

    # Extract text page by page rather than trying to flatten everything in one
    # opaque operation.
    #
    # This is the more explainable design:
    # - page-level extraction failures are easier to reason about
    # - later enhancements can preserve page boundaries if needed
    # - the code stays open to future metadata such as per-page text lengths
    #
    # Even though the first version only returns one combined string, keeping
    # page-wise processing here is the right foundation.
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
        #
        # Resume PDFs often contain inconsistent whitespace:
        # - double newlines
        # - trailing spaces
        # - empty lines from layout artifacts
        #
        # Cleaning per page keeps that mess from compounding when the pages are
        # joined together later.
        normalised_page_text = _normalise_extracted_page_text(raw_page_text)

        if normalised_page_text != "":
            extracted_page_texts.append(normalised_page_text)

    # It is possible for a PDF to parse successfully but still yield no usable
    # text.
    #
    # Common causes include:
    # - image-only scanned CVs
    # - highly unusual PDF structure
    # - extraction limitations in the underlying parser
    #
    # This is not the same thing as successful extraction, so fail clearly.
    if len(extracted_page_texts) == 0:
        raise ResumeTextExtractionError(
            "The resume PDF did not yield any usable text.",
            stage="text_extraction",
            details=[
                {"file_name": file_name},
                {"page_count": page_count},
            ],
        )

    # Join pages with a double newline so the later text still carries some
    # structural hint that page boundaries existed.
    #
    # That is a small but useful compromise:
    # - one plain string is easy to store and pass to an LLM
    # - double newlines preserve a little document rhythm
    # - we avoid over-engineering page segmentation in the first version
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
        "character_count": len(combined_text),
    }


def extract_text_from_docx_bytes(
    *,
    content_bytes: bytes,
    file_name: str | None = None,
) -> dict[str, Any]:
    """
    Extract plain text from DOCX resume bytes.

    Parameters
    ----------
    content_bytes : bytes
        Raw DOCX bytes, typically returned from a transient attachment-download
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
        If the input bytes are empty, the DOCX container cannot be parsed, or
        no usable text can be extracted.

    Example
    -------
    A typical call looks like:

        extract_text_from_docx_bytes(
            content_bytes=downloaded_resume["content_bytes"],
            file_name="Isaiah Perumalla.docx",
        )

    Notes
    -----
    - DOCX files are ZIP containers with XML parts.
    - This helper intentionally uses the Python standard library rather than
      bringing in a heavier Word-processing dependency just to extract text.
    - It currently reads the main document body from `word/document.xml`.
    - That is enough for the common resume case even though DOCX can contain
      much richer structures.

    In plain language:

    - open the DOCX ZIP safely in memory
    - read the main document XML
    - extract paragraph text
    - return one clean text bundle
    """

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

    try:
        with ZipFile(BytesIO(content_bytes)) as archive:
            try:
                document_xml = archive.read("word/document.xml")
            except KeyError as exc:
                raise ResumeTextExtractionError(
                    "The resume DOCX does not contain the main document body.",
                    stage="docx_parse",
                    details=[{"file_name": file_name}],
                ) from exc
    except BadZipFile as exc:
        raise ResumeTextExtractionError(
            "The resume DOCX could not be parsed.",
            stage="docx_parse",
            details=[{"file_name": file_name}],
        ) from exc

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise ResumeTextExtractionError(
            "The resume DOCX XML could not be parsed.",
            stage="docx_parse",
            details=[{"file_name": file_name}],
        ) from exc

    extracted_paragraph_texts = _extract_docx_paragraph_texts(root)

    if len(extracted_paragraph_texts) == 0:
        raise ResumeTextExtractionError(
            "The resume DOCX did not yield any usable text.",
            stage="text_extraction",
            details=[{"file_name": file_name}],
        )

    combined_text = "\n\n".join(extracted_paragraph_texts).strip()

    if combined_text == "":
        raise ResumeTextExtractionError(
            "The extracted resume text became empty after normalisation.",
            stage="text_normalisation",
            details=[{"file_name": file_name}],
        )

    return {
        "text": combined_text,
        "page_count": None,
        "extractor": "docx_xml",
        "file_name": file_name,
        "character_count": len(combined_text),
    }


def extract_text_from_doc_bytes(
    *,
    content_bytes: bytes,
    file_name: str | None = None,
) -> dict[str, Any]:
    """
    Extract plain text from legacy binary Word `.doc` resume bytes.

    Parameters
    ----------
    content_bytes : bytes
        Raw `.doc` bytes from one upstream source attachment or archive member.

    file_name : str | None
        Optional source file name used for metadata and clearer error
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
        If the input bytes are empty, no legacy `.doc` converter is available,
        or the converter cannot turn the file into usable text.

    Examples
    --------
    A typical call looks like:

        extract_text_from_doc_bytes(
            content_bytes=downloaded_resume["content_bytes"],
            file_name="Stephen Edwards CV.doc",
        )

    Notes
    -----
    - Legacy `.doc` files are not ZIP/XML like DOCX files.
    - The shared ingestion layer therefore uses a local converter binary rather
      than trying to hand-roll a binary Word parser.
    - Keeping this logic here means JobAdder, Recruiterflow, Outlook, and
      Dropbox all inherit the same `.doc` support automatically.
    """

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

    antiword_executable = _find_antiword_executable()
    if antiword_executable is None:
        raise ResumeTextExtractionError(
            "Legacy Word `.doc` extraction requires a local antiword executable.",
            stage="input_validation",
            details=[{"file_name": file_name}],
        )

    extracted_text = _extract_text_from_doc_via_antiword(
        content_bytes=content_bytes,
        file_name=file_name,
        antiword_executable=antiword_executable,
    )
    normalised_text = _normalise_extracted_page_text(extracted_text)

    if normalised_text == "":
        raise ResumeTextExtractionError(
            "The resume DOC did not yield any usable text.",
            stage="text_extraction",
            details=[{"file_name": file_name}],
        )

    return {
        "text": normalised_text,
        "page_count": None,
        "extractor": "antiword",
        "file_name": file_name,
        "character_count": len(normalised_text),
    }


def _extract_text_from_doc_via_antiword(
    *,
    content_bytes: bytes,
    file_name: str | None,
    antiword_executable: str,
) -> str:
    """
    Extract plain text from one `.doc` file using `antiword`.

    Examples
    --------
    For a downloaded resume such as `Candidate CV.doc`, this helper:

    1. writes the bytes to a temporary `.doc` file
    2. calls `antiword`
    3. captures stdout as plain text
    4. returns the extracted text to the shared normalisation layer
    """

    safe_file_name = (
        Path(file_name).name
        if isinstance(file_name, str) and file_name.strip() != ""
        else "resume.doc"
    )
    if not safe_file_name.lower().endswith(".doc"):
        safe_file_name = f"{safe_file_name}.doc"

    with TemporaryDirectory(prefix="resume-doc-") as temp_dir:
        temp_path = Path(temp_dir) / safe_file_name
        temp_path.write_bytes(content_bytes)

        try:
            completed_process = subprocess.run(
                [antiword_executable, str(temp_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise ResumeTextExtractionError(
                "Legacy Word `.doc` extraction timed out.",
                stage="doc_parse",
                details=[{"file_name": file_name}],
            ) from exc
        except OSError as exc:
            raise ResumeTextExtractionError(
                "Legacy Word `.doc` extraction could not start the local converter.",
                stage="doc_parse",
                details=[{"file_name": file_name}],
            ) from exc

    if completed_process.returncode != 0:
        raise ResumeTextExtractionError(
            "The resume DOC could not be parsed.",
            stage="doc_parse",
            details=[
                {"file_name": file_name},
                {"converter": antiword_executable},
                {"return_code": completed_process.returncode},
                {"stderr": completed_process.stderr.strip() or None},
            ],
        )

    return completed_process.stdout


def _find_antiword_executable() -> str | None:
    """
    Return a usable `antiword` executable path when one is available locally.

    Examples
    --------
    On a Windows workstation with Git for Windows installed, this may resolve
    to something like:

        C:\\Program Files\\Git\\mingw64\\bin\\antiword.exe
    """

    candidate_paths = [
        shutil.which("antiword"),
        r"C:\Program Files\Git\mingw64\bin\antiword.exe",
        r"C:\Program Files (x86)\Git\mingw64\bin\antiword.exe",
    ]

    for raw_path in candidate_paths:
        if not raw_path:
            continue
        if os.path.isfile(raw_path):
            return raw_path

    return None


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

        "Roger Campbell\\n\\nSenior Data Scientist   \\n\\n"

    becomes something closer to:

        "Roger Campbell\\nSenior Data Scientist"

    Notes
    -----
    - This helper is intentionally conservative.
    - It removes obvious whitespace noise but does not attempt semantic
      rewriting.
    - The goal is to make later extraction more stable, not to "improve" the
      candidate's wording.
    """

    if not isinstance(raw_page_text, str):
        return ""

    # Trim each line individually first.
    #
    # This helps with the common PDF-extraction pattern where the text itself
    # is usable, but each line arrives padded with layout whitespace.
    raw_lines = raw_page_text.splitlines()
    stripped_lines = [line.strip() for line in raw_lines]

    cleaned_lines: list[str] = []
    previous_line_blank = False

    # Collapse repeated blank lines while preserving single blank-line breaks.
    #
    # That gives later LLM or rule-based extraction some natural separation
    # between sections such as:
    # - summary
    # - experience
    # - education
    #
    # without leaving the output full of extraction noise.
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


def _extract_docx_paragraph_texts(root: ElementTree.Element) -> list[str]:
    """
    Extract normalised paragraph text from a parsed DOCX document tree.

    Parameters
    ----------
    root : ElementTree.Element
        Parsed `word/document.xml` root element.

    Returns
    -------
    list[str]
        Non-empty paragraph strings in document order.

    Notes
    -----
    - DOCX text is stored in many `<w:t>` nodes nested inside runs.
    - We rebuild paragraphs one paragraph at a time because that is a simple,
      useful structure for resume text.
    - This helper also treats explicit Word line-break tags as newlines inside
      a paragraph.
    """

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraph_texts: list[str] = []

    # Walk paragraph-by-paragraph so we preserve the basic document rhythm a CV
    # usually relies on:
    # - heading
    # - summary block
    # - employment bullets
    # - education entries
    #
    # That is a better fit for later extraction than flattening every text node
    # into one long line immediately.
    for paragraph in root.findall(".//w:body//w:p", namespace):
        paragraph_fragments: list[str] = []

        # Process the paragraph children in order so explicit line breaks inside
        # one paragraph remain visible instead of being silently discarded.
        for element in paragraph.iter():
            local_name = element.tag.rsplit("}", 1)[-1]

            if local_name == "t" and element.text:
                paragraph_fragments.append(element.text)
            elif local_name in {"br", "cr"}:
                paragraph_fragments.append("\n")
            elif local_name == "tab":
                paragraph_fragments.append("\t")

        normalised_paragraph_text = _normalise_extracted_page_text(
            "".join(paragraph_fragments)
        )

        if normalised_paragraph_text != "":
            paragraph_texts.append(normalised_paragraph_text)

    return paragraph_texts


__all__ = [
    "ResumeTextExtractionError",
    "extract_text_from_doc_bytes",
    "extract_text_from_docx_bytes",
    "extract_text_from_pdf_bytes",
    "extract_text_from_resume_bytes",
]
