from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def fetch_html(url: str, headers: Optional[dict] = None, timeout: int = 20) -> str:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = _session.get(url, headers=merged, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Eventbrite API helpers
# ---------------------------------------------------------------------------

_EVENTBRITE_API_TOKEN = "***REDACTED***"
_EVENTBRITE_HEADERS = {"Authorization": f"Bearer {_EVENTBRITE_API_TOKEN}"}
_EVENTBRITE_TZ = ZoneInfo("America/Los_Angeles")
_EVENTBRITE_API_BASE = "https://www.eventbriteapi.com/v3"


def _eventbrite_get(path: str, params: Optional[dict] = None) -> dict:
    resp = _session.get(
        f"{_EVENTBRITE_API_BASE}{path}",
        headers=_EVENTBRITE_HEADERS,
        params=params or {},
        timeout=10,
    )
    if not resp.ok:
        logger.error(f"Eventbrite API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def _parse_eventbrite_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_EVENTBRITE_TZ)
    except Exception:
        return None


def _parse_eventbrite_event(e: dict, source: str) -> Optional["Event"]:
    from app.event_model import Event

    if e.get("status") != "live":
        return None

    name = (e.get("name") or {}).get("text")
    start = _parse_eventbrite_dt((e.get("start") or {}).get("utc"))

    if not name or not start or start < datetime.now(tz=_EVENTBRITE_TZ):
        return None

    end = _parse_eventbrite_dt((e.get("end") or {}).get("utc"))

    venue = e.get("venue") or {}
    location_parts = [
        venue.get("name"),
        (venue.get("address") or {}).get("localized_address_display"),
    ]
    location = ", ".join([p for p in location_parts if p]) or None

    return Event(
        name=name.strip(),
        start_time=start,
        end_time=end,
        location=location,
        description=(e.get("description") or {}).get("text"),
        source_url=e.get("url"),
        source=source,
        unique_key=Event.build_unique_key(name, start),
    )


def fetch_eventbrite_organizer_events(
    organizer_id: str, source: str, max_pages: int = 10
) -> List["Event"]:
    """Fetch all live upcoming events for an Eventbrite organizer."""
    all_events: list = []
    for page in range(1, max_pages + 1):
        try:
            data = _eventbrite_get(f"/organizers/{organizer_id}/events/", {"page": page})
        except Exception as exc:
            logger.warning(f"[{source}] failed to fetch Eventbrite page {page}: {exc}")
            break

        page_events = [
            ev for e in data.get("events", [])
            if (ev := _parse_eventbrite_event(e, source)) is not None
        ]

        if not page_events:
            logger.info(f"[{source}] no events on Eventbrite page {page}, stopping")
            break

        all_events.extend(page_events)
        logger.info(f"[{source}] Eventbrite page {page}: {len(page_events)} events")

        if not data.get("pagination", {}).get("has_more_items"):
            break

    return all_events


def _eventbrite_event_id(url: str) -> Optional[str]:
    """Extract the numeric event ID from an Eventbrite URL."""
    m = re.search(r"(?:^|[-/])(\d+)(?:/)?$", url.split("?")[0].rstrip("/"))
    return m.group(1) if m else None


def fetch_eventbrite_price(url: str) -> Optional[str]:
    """Return a formatted price string for an Eventbrite event using the API."""
    event_id = _eventbrite_event_id(url)
    if not event_id:
        logger.warning(f"Could not extract Eventbrite event ID from {url}")
        return None
    try:
        data = _eventbrite_get(f"/events/{event_id}/ticket_classes/")
        visible = [tc for tc in data.get("ticket_classes", []) if not tc.get("hidden")]
        if not visible:
            return None
        # Use the lowest priced ticket; free tickets have cost=None and free=True
        def _cents(tc: dict) -> int:
            cost = tc.get("cost")
            return cost["value"] if cost else 0

        cheapest = min(visible, key=_cents)
        cost = cheapest.get("cost")
        if not cost:
            return "Free"
        value = cost.get("value", 0)
        currency = cost.get("currency", "USD")
        return f"${round(value / 100)}"
    except Exception as e:
        logger.warning(f"Failed to fetch Eventbrite price for {url}: {e}")
    return None


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def parse_iso_datetime(s: str):
    """Parse an ISO 8601 datetime string into a timezone-aware datetime."""
    return dtparser.parse(s)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def emit_metric(event_type: str, **fields) -> None:
    """Print a structured JSON entry to stdout for Cloud Logging metric extraction."""
    import sys
    payload = {"event_type": event_type, **fields}
    print(json.dumps(payload), file=sys.stdout, flush=True)
