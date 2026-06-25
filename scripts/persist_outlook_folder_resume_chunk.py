"""
Persist one bounded Outlook folder slice into the canonical schema.

This is the generic operator entrypoint for the Outlook advert-response ingest
path. It reuses the existing implementation that was first proven against the
`tw394` mailbox folder, but exposes it under a reusable script name so later
folders can be ingested without treating `tw394` as a special case.
"""
# ruff: noqa: E402

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.persist_outlook_tw394_folder import main


if __name__ == "__main__":
    raise SystemExit(main())
