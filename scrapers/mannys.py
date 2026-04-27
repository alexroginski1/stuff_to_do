from __future__ import annotations

# Eventbrite organizer endpoint:
# https://www.eventbriteapi.com/v3/organizers/{organizer_id}/events/

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests

from pathlib import Path

from app.event_model import Event

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_ORGANIZER_ID = "15114280512"
_BASE_URL = f"https://www.eventbriteapi.com/v3/organizers/{_ORGANIZER_ID}/events/"
_TZ = ZoneInfo("America/Los_Angeles")

# ⚠️ Hardcoded token (not recommended for production)
_API_TOKEN = "***REDACTED***"

_HEADERS = {
    "Authorization": f"Bearer {_API_TOKEN}",
}

_PAGE_SIZE = 50
_MAX_PAGES = 10


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Eventbrite returns ISO8601 (UTC)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(_TZ)
    except Exception:
        return None


def _fetch_page(page: int) -> dict:
    params = {
        "page": page,

    }

    resp = requests.get(
        _BASE_URL,
        headers=_HEADERS,
        params=params,
        timeout=10
    )

    if not resp.ok:
        logger.error(f"[{_SOURCE}] error response: {resp.text}")
        resp.raise_for_status()

        print(resp.status_code, resp.text)

    return resp.json()

def _parse_page(data: dict) -> List[Event]:
    events: List[Event] = []

    for e in data.get("events", []):
        # Filter only live events (since API param doesn't work)
        if e.get("status") != "live":
            continue

        name = (e.get("name") or {}).get("text")
        url = e.get("url")

        start = _parse_dt((e.get("start") or {}).get("utc"))
        end = _parse_dt((e.get("end") or {}).get("utc"))

        if not name or not start:
            continue

        # Optional: skip past events
        if start < datetime.now(tz=_TZ):
            continue

        venue = e.get("venue") or {}
        location_parts = [
            venue.get("name"),
            (venue.get("address") or {}).get("localized_address_display"),
        ]
        location = ", ".join([p for p in location_parts if p]) or None

        description = (e.get("description") or {}).get("text")

        events.append(Event(
            name=name.strip(),
            start_time=start,
            end_time=end,
            location=location,
            description=description,
            source_url=url,
            source=_SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return events


def fetch_events() -> List[Event]:
    all_events: List[Event] = []

    for page in range(1, _MAX_PAGES + 1):
        try:
            data = _fetch_page(page)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break

        page_events = _parse_page(data)

        if not page_events:
            logger.info(f"[{_SOURCE}] no events on page {page}, stopping")
            break

        all_events.extend(page_events)
        logger.info(f"[{_SOURCE}] page {page}: {len(page_events)} events")

        if not data.get("pagination", {}).get("has_more_items"):
            break

    return all_events