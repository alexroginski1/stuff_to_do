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
_API_URL = "https://astronomyontap.org/wp-json/tribe/events/v1/events?per_page=100&page={page}"
_TZ = ZoneInfo("America/Los_Angeles")

# Astronomy on Tap runs chapters in cities worldwide; only the SF chapter's
# events belong on this calendar.
_CITY = "San Francisco"


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ)
    except ValueError:
        return None


def _clean_description(raw_html: Optional[str]) -> Optional[str]:
    if not raw_html:
        return None
    text = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
    return text or None


def _parse_venue_address(venue: dict) -> Optional[str]:
    address = venue.get("address")
    city = venue.get("city")
    state = venue.get("stateprovince") or venue.get("state")
    parts = [p for p in (address, city, state) if p]
    return ", ".join(parts) if parts else None


def _parse_event(raw: dict) -> Optional[Event]:
    venue = raw.get("venue") or {}
    if venue.get("city") != _CITY:
        return None

    name = html.unescape((raw.get("title") or "").strip())
    start = _parse_dt(raw.get("start_date"))
    if not name or not start:
        return None

    return Event(
        name=name,
        start_time=start,
        end_time=_parse_dt(raw.get("end_date")),
        location=_parse_venue_address(venue),
        description=_clean_description(raw.get("description")),
        source_url=raw.get("url") or _API_URL,
        source=_SOURCE,
    )


def fetch_events() -> List[Event]:
    events: List[Event] = []
    page = 1
    while True:
        try:
            payload = json.loads(fetch_html(_API_URL.format(page=page)))
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break

        events.extend(
            ev for raw in payload.get("events", [])
            if (ev := _parse_event(raw)) is not None
        )

        if page >= payload.get("total_pages", 1):
            break
        page += 1

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
