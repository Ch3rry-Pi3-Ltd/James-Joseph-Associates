"""Print privacy-safe MCP reliability and latency metrics."""

from __future__ import annotations

import argparse
import json

from backend.db.mcp_reporting import get_mcp_operational_summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    print(
        json.dumps(
            get_mcp_operational_summary(hours=args.hours),
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
