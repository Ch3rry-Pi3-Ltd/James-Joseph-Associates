"""Produce a non-destructive review queue for suspicious company labels."""

from __future__ import annotations

import argparse
import json
from typing import Any

from backend.db.companies import list_canonical_company_records
from backend.services.company_name_quality import assess_company_name_quality


def build_company_quality_report(
    records: list[dict[str, Any]],
    *,
    limit: int = 200,
) -> dict[str, Any]:
    review_items: list[dict[str, Any]] = []
    for record in records:
        assessment = assess_company_name_quality(
            str(record.get("name") or ""),
            domain=record.get("domain"),
            website_url=record.get("website_url"),
            linkedin_url=record.get("linkedin_url"),
        )
        if not assessment["needs_review"]:
            continue
        review_items.append(
            {
                "company_id": str(record.get("company_id") or ""),
                "name": str(record.get("name") or ""),
                "quality_flags": assessment["quality_flags"],
                "has_web_identity": assessment["has_web_identity"],
                "source_systems": sorted(record.get("source_systems") or []),
                "source_record_types": sorted(
                    record.get("source_record_types") or []
                ),
            }
        )

    bounded_limit = max(1, min(int(limit), 1000))
    return {
        "canonical_company_count": len(records),
        "needs_review_count": len(review_items),
        "returned_count": min(len(review_items), bounded_limit),
        "review_items": review_items[:bounded_limit],
        "writes_performed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    report = build_company_quality_report(
        list_canonical_company_records(),
        limit=args.limit,
    )
    print(json.dumps(report, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
