from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import parse_iso_datetime

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_SHOP = "black-bird-bookstore.myshopify.com"
_API_URL = f"https://mahina.app/app/{_SHOP}"
_DISPLAY_URL = "https://blackbirdsf.com/pages/events"

_DEFAULT_LOCATION = "4541 Irving St, San Francisco, CA 94122"

# Guards against an infinite loop if the API's reported page count is ever
# wrong or missing.
_MAX_PAGES = 20


def _clean_description(raw_html: Optional[str]) -> Optional[str]:
    if not raw_html:
        return None
    text = BeautifulSoup(raw_html, "html.parser").get_text("\n", strip=True)
    return text or None


def _fetch_page(page: int) -> dict:
    resp = requests.post(
        _API_URL,
        json={"shop": _SHOP, "selectedEventId": None, "selectedRecurringDate": None, "page": page},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_event(raw: dict) -> Optional[Event]:
    name = (raw.get("title") or "").strip()
    start_raw = raw.get("startDate")
    if not name or not start_raw:
        return None

    # The "events" list already contains one entry per occurrence (a
    # recurring event's future dates are pre-expanded server-side), so no
    # recurrence math is needed here.
    start = parse_iso_datetime(start_raw)
    end = parse_iso_datetime(raw["endDate"]) if raw.get("endDate") else None

    # Mahina's `location.medium` is "online" for most of Blackbird's regular
    # in-store programming (Open Mic Night, Writing Club, Storytime, ...) —
    # the venue never bothered to set it to "offline"— so it isn't a
    # reliable signal for whether an event is actually virtual. What *is*
    # reliable is `location.name`: it's only populated for off-site events
    # (e.g. a City Arts & Lectures show at Sydney Goldstein Theater), so fall
    # back to the bookstore's own address whenever it's blank.
    location_name = (raw.get("location") or {}).get("name")
    if location_name:
        location = location_name
        location_verified = False
    else:
        location = _DEFAULT_LOCATION
        location_verified = True

    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=location,
        description=_clean_description(raw.get("description")),
        source_url=_DISPLAY_URL,
        source=_SOURCE,
        location_verified=location_verified,
    )


def fetch_events() -> List[Event]:
    events: List[Event] = []
    num_pages = 1

    page = 1
    while page <= num_pages and page <= _MAX_PAGES:
        try:
            payload = _fetch_page(page)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break

        if page == 1:
            num_pages = int((payload.get("settings") or {}).get("noOfPages") or 1)

        for raw in payload.get("events", []):
            event = _parse_event(raw)
            if event:
                events.append(event)

        page += 1

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
