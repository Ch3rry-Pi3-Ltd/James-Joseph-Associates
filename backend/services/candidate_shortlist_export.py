"""
Recruiter-ready shortlist export helpers.

The export is intentionally generated from the already-grounded shortlist
response. It does not rerun retrieval or call an LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import re
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from backend.services.candidate_resume_files import (
    CandidateResumeFileAccessError,
    fetch_candidate_current_resume_file,
)


def build_candidate_shortlist_export_package(
    *,
    match_run_id: str,
    job_description: str,
    shortlisted_candidates: list[dict[str, Any]],
    role_title: str | None = None,
) -> dict[str, Any]:
    """Build a ZIP containing a Word shortlist and all retrievable CV files."""

    generated_at = datetime.now(timezone.utc)
    resolved_role_title = _derive_role_title(
        role_title=role_title,
        job_description=job_description,
    )
    resume_files: list[dict[str, Any]] = []
    unavailable_resumes: list[dict[str, str]] = []

    for rank, candidate in enumerate(shortlisted_candidates, start=1):
        candidate_id = str(candidate["candidate_id"])
        candidate_name = _clean_optional_text(candidate.get("full_name")) or (
            f"Candidate {rank}"
        )

        try:
            resume_file = fetch_candidate_current_resume_file(candidate_id)
        except CandidateResumeFileAccessError as exc:
            unavailable_resumes.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_name": candidate_name,
                    "reason": exc.message,
                }
            )
            continue

        source_file_name = _clean_optional_text(resume_file.get("file_name")) or (
            f"{candidate_id}.bin"
        )
        archive_file_name = _build_ranked_resume_file_name(
            rank=rank,
            candidate_name=candidate_name,
            source_file_name=source_file_name,
        )
        resume_files.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "archive_file_name": archive_file_name,
                "content_bytes": resume_file["content_bytes"],
                "content_type": resume_file.get("content_type"),
                "document_id": resume_file.get("document_id"),
            }
        )

    document_bytes = _build_shortlist_docx(
        role_title=resolved_role_title,
        match_run_id=match_run_id,
        job_description=job_description,
        shortlisted_candidates=shortlisted_candidates,
        generated_at=generated_at,
        exported_candidate_ids={
            resume_file["candidate_id"] for resume_file in resume_files
        },
    )
    manifest = {
        "match_run_id": match_run_id,
        "role_title": resolved_role_title,
        "generated_at": generated_at.isoformat(),
        "shortlisted_candidate_count": len(shortlisted_candidates),
        "exported_cv_count": len(resume_files),
        "unavailable_cv_count": len(unavailable_resumes),
        "candidates": [
            {
                "rank": rank,
                "candidate_id": str(candidate["candidate_id"]),
                "full_name": candidate.get("full_name"),
                "fit_score": candidate.get("fit_score"),
                "cv_included": str(candidate["candidate_id"])
                in {
                    resume_file["candidate_id"]
                    for resume_file in resume_files
                },
            }
            for rank, candidate in enumerate(shortlisted_candidates, start=1)
        ],
        "unavailable_resumes": unavailable_resumes,
    }

    package_buffer = BytesIO()
    report_file_name = f"Shortlist - {_safe_file_component(resolved_role_title)}.docx"
    with ZipFile(package_buffer, "w", compression=ZIP_DEFLATED) as package:
        package.writestr(report_file_name, document_bytes)
        for resume_file in resume_files:
            package.writestr(
                f"CVs/{resume_file['archive_file_name']}",
                resume_file["content_bytes"],
            )
        package.writestr(
            "export-manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )

    return {
        "content_bytes": package_buffer.getvalue(),
        "file_name": (
            f"Shortlist package - {_safe_file_component(resolved_role_title)}.zip"
        ),
        "exported_cv_count": len(resume_files),
        "unavailable_cv_count": len(unavailable_resumes),
    }


def _build_shortlist_docx(
    *,
    role_title: str,
    match_run_id: str,
    job_description: str,
    shortlisted_candidates: list[dict[str, Any]],
    generated_at: datetime,
    exported_candidate_ids: set[str],
) -> bytes:
    """Create a compact Open XML Word document without another runtime dependency."""

    body_parts = [
        _word_paragraph("Recruiter Shortlist", style="Title"),
        _word_paragraph(role_title, style="Subtitle"),
        _word_paragraph(
            f"Generated {generated_at.strftime('%d %B %Y at %H:%M UTC')}",
            style="Metadata",
        ),
        _word_paragraph(
            f"{len(shortlisted_candidates)} ranked candidates | Match run {match_run_id}",
            style="Metadata",
        ),
        _word_paragraph("Role brief", style="Heading1"),
    ]

    role_brief = _normalize_word_text(job_description)
    if len(role_brief) > 2500:
        role_brief = f"{role_brief[:2497].rstrip()}..."
    body_parts.append(_word_paragraph(role_brief, style="Normal"))
    body_parts.append(_word_paragraph("Ranked candidates", style="Heading1"))

    for rank, candidate in enumerate(shortlisted_candidates, start=1):
        candidate_name = _clean_optional_text(candidate.get("full_name")) or (
            f"Candidate {rank}"
        )
        current_title = _clean_optional_text(candidate.get("current_title"))
        current_company = _clean_optional_text(candidate.get("current_company_name"))
        role_line = current_title or "Current title not available"
        if current_company:
            role_line = f"{role_line} at {current_company}"

        body_parts.extend(
            [
                _word_paragraph(
                    f"{rank}. {candidate_name}",
                    style="Heading2",
                ),
                _word_paragraph(
                    f"Fit {candidate.get('fit_score', 0)}/100 | "
                    f"Retrieval {_format_score(candidate.get('retrieval_score'))}",
                    style="Score",
                ),
                _word_paragraph(role_line, style="CandidateRole"),
                _word_paragraph(
                    _clean_optional_text(candidate.get("fit_summary"))
                    or "No fit summary was returned.",
                    style="Normal",
                ),
                _word_paragraph("Strengths", style="Heading3"),
            ]
        )
        body_parts.extend(
            _word_paragraph(f"• {strength}", style="ListBullet")
            for strength in _string_list(candidate.get("strengths"))
        )
        if not _string_list(candidate.get("strengths")):
            body_parts.append(
                _word_paragraph(
                    "• No strengths were recorded.",
                    style="ListBullet",
                )
            )

        body_parts.append(_word_paragraph("Gaps", style="Heading3"))
        body_parts.extend(
            _word_paragraph(f"• {gap}", style="ListBullet")
            for gap in _string_list(candidate.get("gaps"))
        )
        if not _string_list(candidate.get("gaps")):
            body_parts.append(
                _word_paragraph(
                    "• No material gaps were recorded.",
                    style="ListBullet",
                )
            )

        document_title = _clean_optional_text(candidate.get("document_title"))
        cv_status = (
            f"CV included: {document_title or 'current resume'}"
            if str(candidate["candidate_id"]) in exported_candidate_ids
            else "CV unavailable in this export package"
        )
        body_parts.append(_word_paragraph(cv_status, style="Metadata"))

    body_parts.append(
        (
            "<w:sectPr>"
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
            'w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>'
            "</w:sectPr>"
        )
    )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body_parts)}</w:body>"
        "</w:document>"
    )

    docx_buffer = BytesIO()
    with ZipFile(docx_buffer, "w", compression=ZIP_DEFLATED) as document:
        document.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        document.writestr("_rels/.rels", _DOCX_ROOT_RELATIONSHIPS)
        document.writestr("word/document.xml", document_xml)
        document.writestr("word/styles.xml", _DOCX_STYLES)
        document.writestr(
            "docProps/core.xml",
            _build_core_properties(
                title=f"Recruiter Shortlist - {role_title}",
                generated_at=generated_at,
            ),
        )
        document.writestr("docProps/app.xml", _DOCX_APP_PROPERTIES)

    return docx_buffer.getvalue()


def _word_paragraph(text: str, *, style: str) -> str:
    normalized_text = _normalize_word_text(text)
    space_preserve = ' xml:space="preserve"' if normalized_text.strip() != normalized_text else ""
    return (
        "<w:p>"
        f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        f"<w:r><w:t{space_preserve}>{escape(normalized_text)}</w:t></w:r>"
        "</w:p>"
    )


def _derive_role_title(*, role_title: str | None, job_description: str) -> str:
    normalized_role_title = _clean_optional_text(role_title)
    if normalized_role_title:
        return re.sub(
            r"\.(pdf|docx?|rtf|txt)$",
            "",
            normalized_role_title,
            flags=re.IGNORECASE,
        )[:180]

    title_match = re.search(
        r"\btitle\s*:\s*(.{1,160}?)(?=\s+(?:location|about us|company)\s*:|$)",
        job_description,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if title_match:
        return _normalize_word_text(title_match.group(1))[:180]

    first_line = next(
        (
            line.strip()
            for line in job_description.splitlines()
            if line.strip()
        ),
        "Candidate shortlist",
    )
    first_line = re.sub(
        r"^(job description|role brief)\s*[:\-]?\s*",
        "",
        first_line,
        flags=re.IGNORECASE,
    )
    return first_line[:100].rstrip(" .,:;-") or "Candidate shortlist"


def _build_ranked_resume_file_name(
    *,
    rank: int,
    candidate_name: str,
    source_file_name: str,
) -> str:
    safe_source_name = _safe_file_component(source_file_name)
    suffix_match = re.search(r"(\.[A-Za-z0-9]{1,8})$", safe_source_name)
    suffix = suffix_match.group(1) if suffix_match else ""
    return (
        f"{rank:02d} - {_safe_file_component(candidate_name)}"
        f"{suffix or '.bin'}"
    )


def _safe_file_component(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "shortlist"


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize_word_text(value)
    return normalized or None


def _normalize_word_text(value: str) -> str:
    return re.sub(r"\s+", " ", "".join(character for character in value if ord(character) >= 32)).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        normalized
        for item in value
        if isinstance(item, str)
        and (normalized := _normalize_word_text(item))
    ]


def _format_score(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value:.3f}"
    return "not available"


def _build_core_properties(*, title: str, generated_at: datetime) -> str:
    timestamp = generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title>"
        "<dc:creator>James Joseph Associates</dc:creator>"
        "<cp:lastModifiedBy>James Joseph Associates</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>'
        "</cp:coreProperties>"
    )


_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

_DOCX_ROOT_RELATIONSHIPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

_DOCX_APP_PROPERTIES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>James Joseph Associates</Application>
</Properties>
"""

_DOCX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="21"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:color w:val="27272A"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="0" w:after="100"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="065F46"/><w:sz w:val="48"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle">
    <w:name w:val="Subtitle"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="160"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="18181B"/><w:sz w:val="30"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="300" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="18181B"/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="260" w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="065F46"/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:before="160" w:after="40"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="3F3F46"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="CandidateRole">
    <w:name w:val="Candidate Role"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:b/><w:color w:val="3F3F46"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Score">
    <w:name w:val="Score"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:b/><w:color w:val="047857"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Metadata">
    <w:name w:val="Metadata"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:color w:val="71717A"/><w:sz w:val="18"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListBullet">
    <w:name w:val="List Bullet"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="360" w:hanging="180"/></w:pPr>
    <w:rPr><w:color w:val="27272A"/></w:rPr>
  </w:style>
</w:styles>
"""


__all__ = ["build_candidate_shortlist_export_package"]
