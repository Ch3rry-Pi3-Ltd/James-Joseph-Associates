"""
Text-cleaning helpers for CVs and JobAdder notes.

This module sits between raw text extraction and the first LLM stage.

Why this module exists
----------------------
By this point in the pipeline, the backend can already produce text from
multiple sources such as:

- extracted CV PDF text
- JobAdder candidate notes
- later, possibly email bodies or Dropbox-derived document text

The next problem is different:

    "Can we make that text cleaner and more stable before we ask an LLM
    to reason over it?"

That is what this module is for.

Why this matters
----------------
Raw extracted text is often noisy.

Common problems include:

- broken encoding artifacts such as `Ã‚`
- replacement characters such as `ï¿½`
- excessive blank lines
- trailing whitespace
- inconsistent newline formatting
- boilerplate email disclaimers
- repeated signature blocks
- PDF extraction spacing noise

If we feed that noise directly into later LLM steps, we create avoidable
problems:

- worse extraction quality
- larger prompts than necessary
- more distracting irrelevant content
- less predictable downstream parsing

So this module creates the boundary between:

- raw extracted text, and
- cleaned text ready for later structured extraction

Scope of this first version
---------------------------
This module intentionally stays conservative.

It does:

- normalise line endings
- remove obvious mojibake-style noise
- trim whitespace
- collapse repeated blank lines
- provide source-specific helpers for:
  - resume text
  - JobAdder note text

It does not:

- summarise content
- infer meaning
- classify sections
- remove all email signatures perfectly
- redact personal data
- run an LLM

That restraint is deliberate. The goal is to improve text quality without
quietly changing the meaning of the source material.

Example
-------
A typical caller later in the pipeline might do:

    cleaned_resume_text = clean_resume_text(extracted_resume["text"])
    cleaned_note_text = clean_jobadder_note_text(note["text"])

and receive cleaner, more stable strings that are more suitable for later
prompting and structured extraction.

In plain language:

- take messy source text
- remove the obvious garbage
- keep the meaning intact
- hand the cleaned version to the next stage
"""

from typing import Any


def clean_resume_text(raw_text: Any) -> str:
    """
    Clean extracted resume text conservatively.

    Parameters
    ----------
    raw_text : Any
        Raw resume text, typically produced by the PDF text-extraction layer.

    Returns
    -------
    str
        Cleaned resume text.

    Example
    -------
    A raw value such as:

        "Roger Campbell\\r\\n\\r\\nSenior Data ScientistÃ‚ \\r\\n\\r\\nPython  "

    becomes something closer to:

        "Roger Campbell\\n\\nSenior Data Scientist\\n\\nPython"

    Notes
    -----
    - This helper is intentionally conservative.
    - It removes obvious formatting and encoding noise.
    - It does not attempt to rewrite or summarise resume content.
    - Resume text should preserve section structure where possible, because
      later extraction often depends on cues such as:
      - headings
      - section gaps
      - bullet groupings

    In plain language:

    - normalise the line endings
    - strip broken characters and whitespace noise
    - preserve the broad shape of the CV
    """

    # Start from the shared generic cleaner first.
    #
    # The separation is deliberate:
    # - common low-risk text cleanup lives in one place
    # - source-specific cleanup stays in the thin public helpers
    #
    # That keeps the file easier to extend later if we add:
    # - email-body text cleaning
    # - Outlook-specific cleanup
    # - Dropbox-derived OCR text cleanup
    cleaned_text = _clean_common_text(raw_text)

    # Resume text often benefits from keeping a little more vertical structure
    # than email-style text.
    #
    # We therefore keep the next step deliberately simple:
    # - preserve single blank-line section breaks
    # - remove repeated empty-line noise
    #
    # The goal is not perfect section reconstruction. The goal is to keep the
    # CV readable and stable for later extraction.
    return _collapse_repeated_blank_lines(cleaned_text)


def clean_jobadder_note_text(raw_text: Any) -> str:
    """
    Clean JobAdder note text conservatively.

    Parameters
    ----------
    raw_text : Any
        Raw note text, typically returned by the JobAdder notes endpoint.

    Returns
    -------
    str
        Cleaned JobAdder note text.

    Example
    -------
    A raw value such as:

        "Hi Roger,Ã‚\\r\\n\\r\\nThanks again...\\r\\n\\r\\nWarmest Regards,\\r\\nTomÃ‚ "

    becomes something closer to:

        "Hi Roger,\\n\\nThanks again...\\n\\nWarmest Regards,\\nTom"

    Notes
    -----
    - JobAdder notes often contain email-derived content.
    - That means they can include:
      - encoding artifacts
      - signatures
      - disclaimers
      - reply chains
    - This first version deliberately does not try to strip all of that.
    - It only makes the text cleaner and more readable for later downstream
      logic.

    In plain language:

    - clean the obvious mojibake and whitespace
    - keep the actual note content intact
    - avoid over-editing the recruiter/candidate history
    """

    cleaned_text = _clean_common_text(raw_text)

    # JobAdder notes are often copied from email traffic. In practice that
    # means much of the prompt budget can get wasted on:
    # - legal disclaimers
    # - full signature blocks
    # - repeated quoted reply chains
    #
    # We still keep this conservative:
    # - preserve the main visible message body
    # - strip only the most common boilerplate patterns
    #
    # The goal is not perfect email parsing. The goal is to stop clearly
    # irrelevant note noise from crowding out the useful recruiter/candidate
    # content before it reaches the extraction model.
    cleaned_text = _strip_jobadder_email_boilerplate(cleaned_text)

    return _collapse_repeated_blank_lines(cleaned_text)


def _clean_common_text(raw_text: Any) -> str:
    """
    Apply common low-risk cleanup rules to source text.

    Parameters
    ----------
    raw_text : Any
        Raw text from an upstream source.

    Returns
    -------
    str
        Cleaned text, or an empty string when the input is unusable.

    Example
    -------
    A raw string such as:

        "HelloÃ‚\\r\\n\\r\\nWorld  "

    becomes:

        "Hello\\n\\nWorld"

    Notes
    -----
    - This helper intentionally handles only low-risk cleanup.
    - It is not a semantic transformation step.
    - It exists so multiple source-specific cleaners can reuse the same basic
      normalisation path.
    """

    if not isinstance(raw_text, str):
        return ""

    # Normalize newlines first so all later cleanup rules operate on one
    # consistent text shape.
    #
    # Different sources may contribute:
    # - Windows newlines (`\\r\\n`)
    # - old Mac newlines (`\\r`)
    # - Unix newlines (`\\n`)
    #
    # Converting everything to `\\n` early makes every later rule easier to
    # reason about.
    cleaned_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove the most common mojibake-style garbage we have already seen in
    # real source payloads.
    #
    # These replacements are intentionally narrow. The aim is to remove
    # obvious, repeated junk without introducing aggressive rewriting.
    #
    # Examples we have already seen:
    # - `Ã‚`
    # - replacement characters such as `ï¿½`
    cleaned_text = cleaned_text.replace("Ã‚", "")
    cleaned_text = cleaned_text.replace("ï¿½", "")

    # Strip leading and trailing whitespace from each line rather than only
    # trimming the whole string once.
    #
    # That matters because PDF extraction and email bodies often pad
    # individual lines with layout noise, and later LLM stages do not benefit
    # from that.
    raw_lines = cleaned_text.split("\n")
    stripped_lines = [line.strip() for line in raw_lines]

    # Reassemble the cleaned lines before the blank-line cleanup step.
    #
    # That keeps the responsibilities separate:
    # - this helper removes per-line whitespace noise
    # - the next helper decides how much vertical spacing to keep
    cleaned_text = "\n".join(stripped_lines).strip()

    return cleaned_text


def _collapse_repeated_blank_lines(raw_text: str) -> str:
    """
    Collapse repeated blank lines while preserving single blank-line breaks.

    Parameters
    ----------
    raw_text : str
        Already-cleaned text.

    Returns
    -------
    str
        Text with repeated blank lines reduced to single blank separators.

    Example
    -------
    A value such as:

        "Line 1\\n\\n\\n\\nLine 2\\n\\n\\nLine 3"

    becomes:

        "Line 1\\n\\nLine 2\\n\\nLine 3"

    Notes
    -----
    - This helper is about layout stability, not meaning.
    - Preserving one blank line is often useful because it keeps some section
      structure without letting extracted text balloon with whitespace noise.
    """

    if raw_text == "":
        return ""

    cleaned_lines: list[str] = []
    previous_line_blank = False

    # Walk the text one line at a time so we can control blank-line spacing
    # deliberately rather than relying on a fragile regex.
    #
    # The specific rule we want is:
    # - keep meaningful text lines
    # - allow one blank line as a section separator
    # - discard runs of repeated blank lines
    #
    # That gives us a cleaner result for later prompting:
    # - headings and sections still stay visually separated
    # - but we do not waste prompt space on large blocks of empty lines
    for line in raw_text.split("\n"):
        is_blank = line == ""

        if is_blank:
            # Only keep a blank line when:
            # - the previous kept line was not already blank
            # - and we have already captured some real content
            #
            # This avoids two common problems:
            # - multiple consecutive blank lines expanding the text
            #   unnecessarily
            # - leading blank lines appearing at the very start of the output
            if not previous_line_blank and len(cleaned_lines) > 0:
                cleaned_lines.append("")

            # Record that the most recent processed line was blank so the next
            # iteration can decide whether another blank line should be
            # dropped.
            previous_line_blank = True
            continue

        # Any non-blank line is always worth keeping.
        #
        # Once we keep a real text line, reset the blank-line tracker so a
        # later blank line can be preserved as a legitimate section break.
        cleaned_lines.append(line)
        previous_line_blank = False

    # Reassemble the cleaned lines into one string and trim any accidental
    # whitespace around the edges of the final result.
    return "\n".join(cleaned_lines).strip()


def _strip_jobadder_email_boilerplate(raw_text: str) -> str:
    """
    Remove common email-derived boilerplate from JobAdder note text.

    Parameters
    ----------
    raw_text : str
        Already-cleaned note text.

    Returns
    -------
    str
        Note text with common disclaimer, signature, and reply-chain boilerplate
        removed when those patterns are clear.

    Notes
    -----
    - This helper stays deliberately heuristic and conservative.
    - It targets only recurring note noise that materially harms prompt quality.
    - If no recognizable boilerplate is present, the original text is returned.

    Example
    -------
    A note body such as:

        "Hi Roger, ...\\n\\nWarmest Regards,\\n\\nTom\\n\\nT: ...\\n\\nFrom: Roger ..."

    is reduced toward:

        "Hi Roger, ..."

    In plain language:

    - keep the main message
    - drop the obvious email clutter underneath it
    """

    if raw_text == "":
        return ""

    cleaned_text = _strip_common_email_disclaimer(raw_text)
    cleaned_text = _strip_common_email_signature(cleaned_text)
    cleaned_text = _strip_common_reply_chain(cleaned_text)
    return cleaned_text.strip()


def _strip_common_email_disclaimer(raw_text: str) -> str:
    """
    Remove the common legal disclaimer block seen in email-derived notes.
    """

    disclaimer_markers = [
        "\nThis email and any files transmitted with it are confidential",
        "\nThis message contains confidential information and is intended only",
        "\nIf you are not the intended recipient you are notified that",
    ]

    cut_points = [
        raw_text.find(marker)
        for marker in disclaimer_markers
        if raw_text.find(marker) != -1
    ]

    if not cut_points:
        return raw_text

    return raw_text[: min(cut_points)].rstrip()


def _strip_common_email_signature(raw_text: str) -> str:
    """
    Remove a trailing email signature block when it is clearly present.
    """

    lines = raw_text.split("\n")
    contact_markers = ("T:", "M:", "E:", "L:", "W:", "A:")
    valedictions = {
        "warmest regards,",
        "kind regards,",
        "best regards,",
        "regards,",
        "warm regards,",
    }

    for index, line in enumerate(lines):
        if line.strip().lower() not in valedictions:
            continue

        # Only treat the valediction as the start of a removable signature when
        # the following lines actually look like a contact block. This avoids
        # stripping every casual "Regards," in short genuine notes.
        #
        # Be slightly generous in how far we scan because real email signatures
        # often include blank spacer lines and one or two title/name lines
        # before the obvious contact markers appear.
        trailing_lines = lines[index + 1 : index + 16]
        if any(
            _line_looks_like_signature_contact(candidate_line, contact_markers)
            for candidate_line in trailing_lines
        ):
            return "\n".join(lines[:index]).rstrip()

    return raw_text


def _strip_common_reply_chain(raw_text: str) -> str:
    """
    Remove the start of a quoted email reply chain when it is clearly present.
    """

    reply_markers = [
        "\nFrom: ",
        "\nSent from Outlook for Android",
        "\n-----Original Message-----",
        "\nOriginal Message",
    ]

    cut_points = []
    for marker in reply_markers:
        marker_index = raw_text.find(marker)
        if marker_index > 0:
            cut_points.append(marker_index)

    if not cut_points:
        return raw_text

    return raw_text[: min(cut_points)].rstrip()


def _line_looks_like_signature_contact(
    line: str,
    contact_markers: tuple[str, ...],
) -> bool:
    """
    Return whether a line looks like part of an email signature contact block.

    Notes
    -----
    This helper normalises whitespace before checking the line because copied
    email signatures often contain non-breaking spaces and irregular padding.
    """

    stripped_line = line.replace("\xa0", " ").strip()

    return (
        stripped_line.startswith(contact_markers)
        or "www." in stripped_line.lower()
        or "@" in stripped_line
    )


__all__ = [
    "clean_jobadder_note_text",
    "clean_resume_text",
]
