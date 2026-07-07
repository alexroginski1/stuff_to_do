from __future__ import annotations

import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://www.artbae.info"
# Squarespace exposes the raw collection data for any page via ?format=json;
# this is the "events" collection backing the site's map/calendar block.
_EVENTS_URL = f"{_BASE_URL}/events?format=json"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_dt(ms: Optional[int]) -> Optional[datetime]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=_TZ)


def _strip_duplicate_title(text: str, name: str) -> str:
    """Body text opens by re-rendering the title, sometimes with slightly
    different capitalization/wording (e.g. "De Young Museum" vs "de Young").
    Drop that leading chunk since the name is already shown elsewhere in the
    calendar entry.
    """
    words = text.split()
    name_word_count = len(name.split())
    for window in range(name_word_count, name_word_count + 3):
        candidate = " ".join(words[:window])
        if SequenceMatcher(None, candidate.lower(), name.lower()).ratio() > 0.7:
            return " ".join(words[window:]).strip()
    return text


def _clean_html(html: Optional[str], name: str) -> Optional[str]:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    text = _strip_duplicate_title(text, name)
    return text or None


def _location(raw: dict) -> Optional[str]:
    loc = raw.get("location") or {}
    parts = [loc.get("addressTitle"), loc.get("addressLine1"), loc.get("addressLine2")]
    return ", ".join(p for p in parts if p) or None


def _parse_event(raw: dict) -> Optional[Event]:
    name = (raw.get("title") or "").strip()
    start = _parse_dt(raw.get("startDate"))
    if not name or not start:
        return None

    full_url = raw.get("fullUrl") or ""

    return Event(
        name=name,
        start_time=start,
        end_time=_parse_dt(raw.get("endDate")),
        location=_location(raw),
        description=_clean_html(raw.get("body"), name),
        source_url=f"{_BASE_URL}{full_url}" if full_url else _EVENTS_URL,
        source=_SOURCE,
    )


def fetch_events() -> List[Event]:
    try:
        payload = json.loads(fetch_html(_EVENTS_URL))
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch events: {exc}")
        return []

    events = [
        ev for raw in payload.get("upcoming", [])
        if (ev := _parse_event(raw)) is not None
    ]

    logger.info(f"[{_SOURCE}] parsed {len(events)} events")
    return events
