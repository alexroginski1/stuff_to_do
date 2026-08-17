from __future__ import annotations

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
_URL = "https://rootdivision.org/gallery/events/"
_ADDRESS = "1131 Mission Street, San Francisco, CA 94103"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_start(date_str: str) -> Optional[datetime]:
    """date_str looks like "Aug 19, 2026 6:00 pm | Meeting" — only the
    leading "Aug 19, 2026 6:00 pm" chunk is the date/time."""
    chunk = date_str.split("|")[0].strip()
    try:
        return datetime.strptime(chunk, "%b %d, %Y %I:%M %p").replace(tzinfo=_TZ)
    except ValueError:
        return None


def _parse_event(li) -> Optional[Event]:
    title_el = li.select_one("h4 a")
    if not title_el:
        return None
    name = title_el.get_text(strip=True)
    url = title_el.get("href") or _URL

    date_el = li.select_one("h4 + div")
    if not date_el:
        return None
    start = _parse_start(date_el.get_text(" ", strip=True))
    if not start:
        return None

    desc_el = date_el.find_next_sibling("div")
    description = desc_el.get_text(" ", strip=True) if desc_el else None

    return Event(
        name=name,
        start_time=start,
        end_time=None,
        location=_ADDRESS,
        description=description or None,
        source_url=url,
        source=_SOURCE,
        location_verified=True,
    )


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for li in soup.select("ul.eo-events > li"):
        event = _parse_event(li)
        if event:
            events.append(event)
    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
