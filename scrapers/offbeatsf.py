from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_DISPLAY_URL = "https://offbeatsf.com/events/"
_API_URL = "https://offbeatsf.com/wp-json/tribe/events/v1/events"
_TZ = ZoneInfo("America/Los_Angeles")

# Backed by The Events Calendar's public REST API, which paginates ~50
# events per page across the site's entire multi-year backlog of daily SF
# live-music listings. start_date/end_date scope the query server-side to
# the sync engine's lookahead window (app/sync_engine.py _LOOKAHEAD_DAYS)
# plus a buffer, so a run only ever has to page through a handful of pages.
_PER_PAGE = 50
_HORIZON_DAYS = 9
_MAX_PAGES = 10


def _parse_local(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ)
    except ValueError:
        return None


def _clean_body(raw_html: Optional[str]) -> Optional[str]:
    if not raw_html:
        return None
    text = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
    return text or None


def _location(venue: dict) -> Optional[str]:
    name = venue.get("venue")
    address = venue.get("address")
    city = venue.get("city")
    if not address or not city:
        return name or None
    state = venue.get("state")
    zip_code = venue.get("zip")
    tail = f"{city}, {state} {zip_code}".strip() if state else city
    line = f"{address}, {tail}"
    return f"{name}, {line}" if name else line


def _description(raw: dict) -> Optional[str]:
    cost = (raw.get("cost") or "").strip()
    body = _clean_body(raw.get("description"))
    if cost and body:
        return f"Price: {cost}\n\n{body}"
    if cost:
        return f"Price: {cost}"
    return body


def _fetch_page(start: str, end: str, page: int) -> dict:
    url = f"{_API_URL}?per_page={_PER_PAGE}&page={page}&start_date={start}&end_date={end}"
    return json.loads(fetch_html(url))


def _parse_event(raw: dict) -> Optional[Event]:
    name = html.unescape((raw.get("title") or "").strip())
    start = _parse_local(raw.get("start_date"))
    if not name or not start:
        return None

    venue = raw.get("venue")
    if not isinstance(venue, dict):
        venue = {}
    return Event(
        name=name,
        start_time=start,
        end_time=_parse_local(raw.get("end_date")),
        location=_location(venue),
        description=_description(raw),
        source_url=raw.get("url") or _DISPLAY_URL,
        source=_SOURCE,
        location_verified=bool(venue.get("address")),
    )


def fetch_events() -> List[Event]:
    today = datetime.now(tz=_TZ).date()
    horizon = today + timedelta(days=_HORIZON_DAYS)
    start, end = today.isoformat(), horizon.isoformat()

    raw_events: List[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        try:
            data = _fetch_page(start, end, page)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break
        page_events = data.get("events") or []
        if not page_events:
            break
        raw_events.extend(page_events)
        if page >= (data.get("total_pages") or 1):
            break

    events = [ev for raw in raw_events if (ev := _parse_event(raw)) is not None]

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
