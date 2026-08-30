from __future__ import annotations

import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://www.specsbarsf.com"
_EVENTS_URL = f"{_BASE_URL}/events?format=json"
_TZ = ZoneInfo("America/Los_Angeles")

# Squarespace's own location field is unset for every listing here (just
# default map coordinates with no address), so hardcode the venue's actual
# address rather than trusting it.
_LOCATION = "12 William Saroyan Place, San Francisco, CA 94133"


def _parse_dt(ms: Optional[int]) -> Optional[datetime]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=_TZ)


def _clean_body(raw_html: Optional[str]) -> Optional[str]:
    if not raw_html:
        return None
    text = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
    return text or None


def _parse_event(raw: dict) -> Optional[Event]:
    name = html.unescape((raw.get("title") or "").strip())
    if not name:
        return None

    start = _parse_dt(raw.get("startDate"))
    if not start:
        return None

    full_url = raw.get("fullUrl") or ""

    return Event(
        name=name,
        start_time=start,
        end_time=_parse_dt(raw.get("endDate")),
        location=_LOCATION,
        description=_clean_body(raw.get("body")),
        source_url=f"{_BASE_URL}{full_url}" if full_url else _EVENTS_URL,
        source=_SOURCE,
        location_verified=True,
    )


def fetch_events() -> List[Event]:
    try:
        payload = json.loads(fetch_html(_EVENTS_URL))
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events = [
        ev for raw in payload.get("upcoming", [])
        if (ev := _parse_event(raw)) is not None
    ]

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
