"""
Post one or more Linked Helper person/contact payloads to the protected backend route.

This script exists for one operational purpose:

    "Take a Linked Helper webhook/CSV-transformed JSON payload and persist it
    into the canonical backend without hand-building HTTP requests."
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_API_BASE_URL = "https://james-joseph-associates.vercel.app"


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for Linked Helper person/contact ingestion.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Post one or more Linked Helper person/contact payloads to the "
            "protected backend route."
        )
    )
    parser.add_argument(
        "--payload-file",
        required=True,
        help=(
            "Path to a JSON file containing either one payload object or a "
            "list of payload objects."
        ),
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Backend base URL hosting the protected Linked Helper ingest route.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause between payload posts.",
    )
    return parser


def load_local_env() -> dict[str, str]:
    """
    Load a small `.env.local` key-value mapping for local operator scripts.
    """

    env: dict[str, str] = {}
    env_path = pathlib.Path(".env.local")
    if not env_path.exists():
        return env

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key.strip()] = value
    return env


def load_admin_token() -> str:
    """
    Load the bearer token expected by protected admin routes.
    """

    env = load_local_env()
    admin_token = (
        env.get("ADMIN_API_TOKEN")
        or env.get("INTERNAL_ADMIN_API_TOKEN")
        or env.get("MAKE_API_TOKEN")
    )
    if not admin_token:
        raise RuntimeError("No admin token found in .env.local")
    return admin_token


def load_payloads(payload_file: str) -> list[dict[str, Any]]:
    """
    Load one or more Linked Helper ingest payloads from disk.
    """

    payload_path = pathlib.Path(payload_file)
    loaded = json.loads(payload_path.read_text(encoding="utf-8"))

    if isinstance(loaded, dict):
        return [loaded]

    if isinstance(loaded, list) and all(isinstance(item, dict) for item in loaded):
        return list(loaded)

    raise RuntimeError(
        "Payload file must contain either one JSON object or a list of JSON objects."
    )


def call_ingest_route(
    *,
    api_base_url: str,
    admin_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Call the protected Linked Helper ingest route and return the parsed JSON body.
    """

    base_url = api_base_url.rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/api/v1/integrations/linkedin-helper/admin/ingest-person",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_text = response.read().decode("utf-8")
            return json.loads(response_text)
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8")
        raise RuntimeError(
            f"Linked Helper ingest route failed with HTTP {exc.code}: {response_text}"
        ) from exc


def build_payload_label(payload: dict[str, Any]) -> str:
    """
    Build a concise operator-facing label for one payload.
    """

    return (
        str(payload.get("source_record_id"))
        if payload.get("source_record_id")
        else (
            str(payload.get("linkedin_url"))
            if payload.get("linkedin_url")
            else str(payload.get("full_name") or payload.get("first_name") or "unknown")
        )
    )


def main() -> None:
    """
    Run one or more Linked Helper ingest payloads against the protected route.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    admin_token = load_admin_token()
    payloads = load_payloads(args.payload_file)

    totals = {
        "payload_count": len(payloads),
        "completed_count": 0,
        "failed_count": 0,
    }

    for index, payload in enumerate(payloads):
        response_payload = call_ingest_route(
            api_base_url=args.api_base_url,
            admin_token=admin_token,
            payload=payload,
        )
        print(
            json.dumps(
                {
                    "index": index,
                    "label": build_payload_label(payload),
                    "status": response_payload.get("status"),
                    "persisted": response_payload.get("persisted", {}),
                }
            )
        )
        totals["completed_count"] += 1

        if args.pause_seconds > 0 and index < len(payloads) - 1:
            time.sleep(args.pause_seconds)

    print(json.dumps({"totals": totals}))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
