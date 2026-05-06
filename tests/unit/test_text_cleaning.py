"""
Unit tests for text-cleaning helpers.

This module tests the conservative cleanup layer in
`backend.services.text_cleaning`.

Why these tests matter
----------------------
By this point in the ingestion pipeline, the backend can already produce raw
text from sources such as:

- extracted CV PDFs
- JobAdder candidate notes

The next question is different:

    "Can we clean that text just enough to make later LLM extraction more
    stable, without quietly changing its meaning?"

That matters because the text-cleaning layer sits directly on the critical path
to the first structured LLM stage.

If this layer behaves badly, the downstream effects can include:

- larger and noisier prompts
- worse extraction quality
- unstable formatting for later parsing
- accidental loss of useful section structure

These tests therefore protect the low-risk cleanup rules before they are wired
into the broader ingest flow.

Scope of these tests
--------------------
These tests intentionally do not:

- call external APIs
- parse PDFs
- run an LLM
- write to the database

Instead, they focus only on the local behaviour of:

- `clean_resume_text(...)`
- `clean_jobadder_note_text(...)`
- `_clean_common_text(...)`
- `_collapse_repeated_blank_lines(...)`

Example
-------
A typical test in this module checks that a raw string such as:

    "HelloÃ‚\\r\\n\\r\\nWorld  "

becomes:

    "Hello\\n\\nWorld"

In plain language:

- give the cleaner messy source text
- confirm it removes obvious noise
- confirm it preserves the underlying meaning and structure
"""

import backend.services.text_cleaning as text_cleaning


def test_clean_resume_text_normalises_newlines_and_removes_mojibake() -> None:
    """
    Verify that the resume-text cleaner removes obvious encoding noise and
    normalises line endings while preserving broad CV structure.

    Notes
    -----
    - Resume text often comes from PDF extraction, so it commonly contains:
      - `\\r\\n` or `\\r`
      - trailing spaces
      - mojibake such as `Ã‚`
    - The helper should clean those issues without flattening the structure
      into one dense paragraph.

    Example
    -------
    A raw value such as:

        "Roger Campbell\\r\\n\\r\\nSenior Data ScientistÃ‚ \\r\\n\\r\\nPython  "

    should become:

        "Roger Campbell\\n\\nSenior Data Scientist\\n\\nPython"

    In plain language:

    - feed in messy extracted CV text
    - confirm the cleaner returns a stable, readable version
    """

    raw_text = "Roger Campbell\r\n\r\nSenior Data ScientistÃ‚ \r\n\r\nPython  "

    cleaned_text = text_cleaning.clean_resume_text(raw_text)

    assert cleaned_text == "Roger Campbell\n\nSenior Data Scientist\n\nPython"


def test_clean_resume_text_repairs_common_pdf_heading_spacing() -> None:
    """
    Verify that the resume-text cleaner repairs the specific heading-spacing
    corruption we have seen in live PDF extraction output.

    Notes
    -----
    - This is a targeted fix, not a generic OCR reconstruction system.
    - The intent is to repair clearly broken section headings such as:
      - `Exp eri enc e`
      - `Sk i l ls`
      - `Ed uc a t i o n`
    - These fragments are real prompt noise and should be normalised before the
      extraction model sees them.

    Example
    -------
    A raw value such as:

        "Exp eri enc e\\nSk i l ls\\nEd uc a t i o n"

    should become:

        "Experience\\nSkills\\nEducation"

    In plain language:

    - fix the known broken headings
    - leave the rest of the resume structure intact
    """

    raw_text = "Exp eri enc e\r\nSk i l ls\r\nEd uc a t i o n"

    cleaned_text = text_cleaning.clean_resume_text(raw_text)

    assert cleaned_text == "Experience\nSkills\nEducation"


def test_clean_jobadder_note_text_preserves_content_while_cleaning_noise() -> None:
    """
    Verify that the JobAdder note cleaner removes obvious text noise but keeps
    the actual note content readable and structurally intact.

    Notes
    -----
    - JobAdder notes often originate from email bodies.
    - That means they can contain:
      - mojibake
      - trailing whitespace
      - repeated blank lines
    - This first version of the cleaner should improve readability without
      aggressively stripping content such as signatures or reply chains.

    Example
    -------
    A raw note such as:

        "Hi Roger,Ã‚\\r\\n\\r\\nThanks again...\\r\\n\\r\\nWarmest Regards,\\r\\nTomÃ‚ "

    should become:

        "Hi Roger,\\n\\nThanks again...\\n\\nWarmest Regards,\\nTom"

    In plain language:

    - feed in messy JobAdder note text
    - confirm the cleaner removes the obvious junk
    - confirm the useful text remains
    """

    raw_text = "Hi Roger,Ã‚\r\n\r\nThanks again...\r\n\r\nWarmest Regards,\r\nTomÃ‚ "

    cleaned_text = text_cleaning.clean_jobadder_note_text(raw_text)

    assert cleaned_text == "Hi Roger,\n\nThanks again...\n\nWarmest Regards,\nTom"


def test_clean_jobadder_note_text_strips_signature_disclaimer_and_reply_chain_noise() -> None:
    """
    Verify that the JobAdder note cleaner removes the most common email-derived
    clutter that would otherwise dominate the later extraction prompt.

    Notes
    -----
    - This test covers the stronger note-cleaning path added after the first
      live extraction review.
    - The aim is not perfect email parsing.
    - The aim is to keep the main recruiter/candidate message while removing:
      - trailing signature blocks
      - legal disclaimers
      - quoted reply-chain content

    Example
    -------
    A long email-derived note such as:

        "Hi Roger ...\\n\\nWarmest Regards,\\nTom\\nT: ...\\n\\nFrom: Roger ..."

    should be reduced to the meaningful main message only.

    In plain language:

    - keep the real note body
    - strip the repetitive email clutter underneath it
    """

    raw_text = (
        "Hi Roger,\r\n\r\n"
        "I'm just checking if this email is coming through for you?\r\n\r\n"
        "Warmest Regards,\r\n\r\n"
        "Tom\r\n"
        "T: 0203-371-0617\r\n"
        "E: tom.owens@example.com\r\n\r\n"
        "This email and any files transmitted with it are confidential and intended solely for the use of the individual or entity to whom they are addressed.\r\n\r\n"
        "From: Roger Campbell <the_rfc@hotmail.co.uk>\r\n"
        "Sent: 04 March 2026 12:48\r\n"
        "To: Tom Owens <tom.owens@example.com>\r\n"
    )

    cleaned_text = text_cleaning.clean_jobadder_note_text(raw_text)

    assert cleaned_text == (
        "Hi Roger,\n\nI'm just checking if this email is coming through for you?"
    )


def test_clean_common_text_returns_empty_string_for_non_string_input() -> None:
    """
    Verify that the shared common-cleanup helper rejects non-string input
    safely by returning an empty string.

    Notes
    -----
    - This helper is intentionally tolerant rather than exception-heavy.
    - At this layer, non-string text input is best treated as "nothing usable
      to clean" rather than a hard failure.

    In plain language:

    - pass a non-string value
    - confirm the cleaner returns an empty string
    """

    assert text_cleaning._clean_common_text(None) == ""
    assert text_cleaning._clean_common_text(123) == ""
    assert text_cleaning._clean_common_text(["not", "text"]) == ""


def test_clean_common_text_normalises_newlines_trims_lines_and_removes_known_garbage() -> None:
    """
    Verify that the shared common-cleanup helper performs the low-risk text
    cleanup rules it was designed to own.

    Notes
    -----
    - This test protects the most reusable part of the cleaning layer.
    - The helper should:
      - normalise `\\r\\n` and `\\r` into `\\n`
      - strip per-line whitespace
      - remove known mojibake tokens such as `Ã‚` and `ï¿½`

    Example
    -------
    A raw string such as:

        "  HelloÃ‚\\r\\n\\rWorldï¿½  "

    should become:

        "Hello\\n\\nWorld"

    In plain language:

    - give the common helper a messy mixed-format string
    - confirm it applies the shared cleanup rules correctly
    """

    raw_text = "  HelloÃ‚\r\n\rWorldï¿½  "

    cleaned_text = text_cleaning._clean_common_text(raw_text)

    assert cleaned_text == "Hello\n\nWorld"


def test_clean_common_text_repairs_common_live_mojibake_sequences() -> None:
    """
    Verify that the common cleaner repairs the recurring mojibake patterns we
    have now seen in live resume and note payloads.

    Notes
    -----
    - This is a real quality issue, not a cosmetic test.
    - The extraction input has shown corruption such as:
      - `4 yearsâ€™ experience`
      - `2022 â€“ 2023`
      - `Â£450`
      - `94.3% Â· 2024`
    - Those patterns should be normalised before prompting the model.
    """

    raw_text = (
        "4 yearsâ€™ experience\r\n"
        "2022 â€“ 2023\r\n"
        "was on Â£450 per day\r\n"
        "Current average: 94.3% Â· 2024 Deanâ€™s List"
    )

    cleaned_text = text_cleaning._clean_common_text(raw_text)

    assert cleaned_text == (
        "4 years’ experience\n"
        "2022 – 2023\n"
        "was on £450 per day\n"
        "Current average: 94.3% · 2024 Dean’s List"
    )


def test_repair_common_pdf_heading_spacing_does_not_flatten_normal_content() -> None:
    """
    Verify that the heading-repair helper does not aggressively rewrite normal
    resume content.

    Notes
    -----
    - The new spacing fix must stay conservative.
    - It should normalise broken section headings, but it should not rewrite
      ordinary lines such as:
        - `Data Science & AI`
        - `Open University`
        - short sentence content

    Example
    -------
    A value such as:

        "Data Science & AI\\nOpen University"

    should be returned unchanged.

    In plain language:

    - prove the fix is narrowly targeted
    - avoid accidental over-cleaning
    """

    raw_text = "Data Science & AI\nOpen University"

    cleaned_text = text_cleaning._repair_common_pdf_heading_spacing(raw_text)

    assert cleaned_text == "Data Science & AI\nOpen University"


def test_collapse_repeated_blank_lines_preserves_single_section_breaks() -> None:
    """
    Verify that the blank-line collapse helper removes repeated blank runs
    while preserving one blank line as a section separator.

    Notes
    -----
    - This is the key layout rule for keeping cleaned text readable.
    - We do not want:
      - large blocks of empty lines
    - But we also do not want:
      - zero section separation
    - So the helper should keep one blank line where appropriate.

    Example
    -------
    A value such as:

        "Line 1\\n\\n\\n\\nLine 2\\n\\n\\nLine 3"

    should become:

        "Line 1\\n\\nLine 2\\n\\nLine 3"

    In plain language:

    - pass in text with too many blank lines
    - confirm the helper keeps only the useful spacing
    """

    raw_text = "Line 1\n\n\n\nLine 2\n\n\nLine 3"

    cleaned_text = text_cleaning._collapse_repeated_blank_lines(raw_text)

    assert cleaned_text == "Line 1\n\nLine 2\n\nLine 3"


def test_collapse_repeated_blank_lines_removes_leading_and_trailing_blank_padding() -> None:
    """
    Verify that the blank-line collapse helper does not preserve empty padding
    at the very start or end of the text.

    Notes
    -----
    - Leading and trailing blank lines are usually just formatting noise.
    - The helper should therefore return a trimmed result even if the input
      starts or ends with repeated empty lines.

    Example
    -------
    A value such as:

        "\\n\\n\\nLine 1\\n\\nLine 2\\n\\n\\n"

    should become:

        "Line 1\\n\\nLine 2"

    In plain language:

    - pass in text padded with blank lines around the edges
    - confirm the helper removes that padding
    """

    raw_text = "\n\n\nLine 1\n\nLine 2\n\n\n"

    cleaned_text = text_cleaning._collapse_repeated_blank_lines(raw_text)

    assert cleaned_text == "Line 1\n\nLine 2"
