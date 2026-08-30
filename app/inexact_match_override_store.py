from __future__ import annotations

import csv
import io
import logging
import re

from app.utils import fetch_html

logger = logging.getLogger(__name__)

# The "inexact_match_manual_update" tab of the shared location-corrections
# sheet: https://docs.google.com/spreadsheets/d/1x1EeFDPKNDULmW1_EE-4xsTcPV0RQ7pdZd4oK_fh0Dg
# Columns are "inexact" (a raw location string Places couldn't resolve
# cleanly) and "exact" (the correct address to use instead, already in
# Places' output format). Read directly as a CSV export rather than through
# the Sheets API — the tab is publicly viewable, same pattern as
# scrapers/setup_comedy.py's published-sheet CSV fetch.
_SHEET_ID = "1x1EeFDPKNDULmW1_EE-4xsTcPV0RQ7pdZd4oK_fh0Dg"
_GID = "326775793"
_CSV_URL = f"https://docs.google.com/spreadsheets/d/{_SHEET_ID}/export?format=csv&gid={_GID}"

# Loaded lazily and kept for the life of the process (one scheduler run), the
# same lifetime as location_service._cache — a fresh process re-reads the
# sheet, so edits to it take effect on the next run without a redeploy.
_overrides: dict[str, str] | None = None


def _normalize(text: str) -> str:
    """Collapse a location string down to just its letters/digits, lowercased.

    Lets e.g. "Jessie Square, 736 Mission St." and "jessie square 736
    mission st" match despite whitespace/punctuation/case differences —
    matching is meant to ignore anything but the actual characters, per how
    the sheet is used.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _load_overrides() -> dict[str, str]:
    global _overrides
    if _overrides is not None:
        return _overrides

    overrides: dict[str, str] = {}
    try:
        csv_text = fetch_html(_CSV_URL)
        for row in csv.DictReader(io.StringIO(csv_text)):
            inexact = (row.get("inexact") or "").strip()
            exact = (row.get("exact") or "").strip()
            if inexact and exact:
                overrides[_normalize(inexact)] = exact
    except Exception as exc:
        logger.error(f"Failed to load inexact_match_manual_update sheet: {exc}")

    _overrides = overrides
    return _overrides


def find_override(raw_location: str) -> str | None:
    """Return the manually-curated exact address for `raw_location`, or None if it isn't in the sheet.

    Looked up by normalized match (see `_normalize`) against the sheet's
    "inexact" column, so whitespace/punctuation/case differences between the
    raw location string and what's typed into the sheet don't cause a miss.
    """
    return _load_overrides().get(_normalize(raw_location))
