"""Deterministic groundedness, stability, and sensitive-data checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Iterable


DEFAULT_VOLATILE_FIELDS = frozenset(
    {
        "created_at",
        "duration_ms",
        "match_run_id",
        "request_id",
        "updated_at",
    }
)
PUBLIC_FORBIDDEN_FIELDS = frozenset(
    {
        "authorization",
        "contact_email",
        "contact_phone",
        "mcp_api_token",
        "primary_email",
        "primary_phone",
        "token",
    }
)
REQUIRED_RAG_FAILURE_ACTIONS = {
    "missing_evidence": "block_generation",
    "stale_evidence": "flag_for_review",
    "conflicting_evidence": "flag_for_review",
    "noisy_evidence": "ignore_low_signal",
    "malicious_evidence": "treat_as_untrusted_data",
    "provider_timeout": "fail_closed",
    "malformed_output": "reject_output",
}


@dataclass(frozen=True)
class QualityFinding:
    """One safe evaluation failure without raw recruitment data."""

    code: str
    path: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def validate_claim_evidence(
    *,
    claim_groups: dict[str, list[dict[str, Any]]],
    allowed_evidence_refs: Iterable[str],
) -> list[QualityFinding]:
    """Require every generated claim to cite known, retrievable evidence."""

    allowed_refs = {str(value) for value in allowed_evidence_refs}
    findings: list[QualityFinding] = []
    for group_name, claims in claim_groups.items():
        for index, claim in enumerate(claims):
            claim_path = f"{group_name}[{index}]"
            refs = [
                str(value).strip()
                for value in claim.get("evidence_refs", [])
                if str(value).strip()
            ]
            if not refs:
                findings.append(
                    QualityFinding(
                        code="missing_evidence_reference",
                        path=claim_path,
                        detail="Generated claim has no evidence reference.",
                    )
                )
                continue

            unknown_count = sum(ref not in allowed_refs for ref in refs)
            if unknown_count:
                findings.append(
                    QualityFinding(
                        code="unknown_evidence_reference",
                        path=claim_path,
                        detail=(
                            f"Generated claim cites {unknown_count} unknown "
                            "evidence reference(s)."
                        ),
                    )
                )
    return findings


def stable_payload_fingerprint(
    payload: Any,
    *,
    ignored_fields: Iterable[str] = DEFAULT_VOLATILE_FIELDS,
) -> str:
    """Return a stable digest after removing run-specific metadata."""

    ignored = {str(field) for field in ignored_fields}
    canonical = _canonicalize(payload, ignored_fields=ignored)
    serialized = json.dumps(
        canonical,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def find_sensitive_fields(
    payload: Any,
    *,
    forbidden_fields: Iterable[str] = PUBLIC_FORBIDDEN_FIELDS,
) -> list[QualityFinding]:
    """Find forbidden field names without copying their values into findings."""

    forbidden = {str(field).casefold() for field in forbidden_fields}
    findings: list[QualityFinding] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key)
                item_path = f"{path}.{key_text}" if path else key_text
                if key_text.casefold() in forbidden and item not in (None, "", []):
                    findings.append(
                        QualityFinding(
                            code="sensitive_field_exposed",
                            path=item_path,
                            detail="Public payload contains a restricted field.",
                        )
                    )
                visit(item, item_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(payload, "")
    return findings


def validate_rag_failure_matrix(cases: list[dict[str, Any]]) -> list[QualityFinding]:
    """Validate complete, unique failure coverage and fail-closed actions."""

    findings: list[QualityFinding] = []
    seen_categories: set[str] = set()
    for index, case in enumerate(cases):
        category = str(case.get("category") or "")
        action = str(case.get("expected_action") or "")
        path = f"cases[{index}]"
        if category in seen_categories:
            findings.append(
                QualityFinding(
                    code="duplicate_failure_category",
                    path=path,
                    detail="Failure category appears more than once.",
                )
            )
        seen_categories.add(category)
        expected_action = REQUIRED_RAG_FAILURE_ACTIONS.get(category)
        if expected_action is not None and action != expected_action:
            findings.append(
                QualityFinding(
                    code="unsafe_failure_action",
                    path=path,
                    detail="Failure category does not use its required safe action.",
                )
            )

    missing = sorted(set(REQUIRED_RAG_FAILURE_ACTIONS) - seen_categories)
    for category in missing:
        findings.append(
            QualityFinding(
                code="missing_failure_category",
                path="cases",
                detail=f"Failure matrix is missing category: {category}.",
            )
        )
    return findings


def _canonicalize(value: Any, *, ignored_fields: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item, ignored_fields=ignored_fields)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in ignored_fields
        }
    if isinstance(value, list):
        return [_canonicalize(item, ignored_fields=ignored_fields) for item in value]
    if isinstance(value, tuple):
        return [_canonicalize(item, ignored_fields=ignored_fields) for item in value]
    return value


__all__ = [
    "DEFAULT_VOLATILE_FIELDS",
    "PUBLIC_FORBIDDEN_FIELDS",
    "QualityFinding",
    "REQUIRED_RAG_FAILURE_ACTIONS",
    "find_sensitive_fields",
    "stable_payload_fingerprint",
    "validate_claim_evidence",
    "validate_rag_failure_matrix",
]
