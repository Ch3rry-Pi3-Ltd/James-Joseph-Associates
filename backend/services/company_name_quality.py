"""Deterministic, non-destructive company-name quality checks."""

from __future__ import annotations

from typing import Any


def assess_company_name_quality(
    name: str,
    *,
    domain: str | None = None,
    website_url: str | None = None,
    linkedin_url: str | None = None,
) -> dict[str, Any]:
    """Return conservative review flags without modifying the supplied name."""

    normalized_name = " ".join(str(name or "").split())
    folded_name = normalized_name.casefold()
    flags: list[str] = []

    generic_suffixes = (
        " company",
        " organisation",
        " organization",
        " business",
        " firm",
    )
    if folded_name.startswith(("a ", "an ", "the ")) and folded_name.endswith(
        generic_suffixes
    ):
        flags.append("possible_generic_description")
    if ":" in normalized_name and folded_name.startswith(("a ", "an ", "the ")):
        flags.append("possible_extraction_fragment")
    if folded_name in {
        "confidential",
        "confidential company",
        "undisclosed",
        "unknown company",
        "stealth company",
    }:
        flags.append("placeholder_company_name")

    identity_fields_present = any(
        str(value or "").strip() for value in (domain, website_url, linkedin_url)
    )
    return {
        "quality_flags": flags,
        "needs_review": bool(flags),
        "has_web_identity": identity_fields_present,
    }


__all__ = ["assess_company_name_quality"]
