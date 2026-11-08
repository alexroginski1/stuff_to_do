from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from app.event_model import Event
from app.tracked_event_store import EventGone, collect_explore_events
from app.utils import fetch_html, parse_iso_datetime
from config.settings import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

# Every Partiful-backed source lives in this one module. Each keeps its own
# source name (config.settings.SOURCES key, with "module": "partiful") so its
# calendar events stay tagged the same; app/sync_engine.py calls
# fetch_events(<source name>).
_EXPLORE_SOURCE = "partiful"

# Host/community pages (partiful.com/u/<user_id>), keyed by source name.
_HOST_USER_IDS = {
    "gathersf": "HoM5CgWY4UxtI5vu9HtU",
    "golden_gate_walk_club": "Uqyv9rLfCdfoExUq88h9",
    "luz_circle": "9ysLpxe3H5cOS5cOS0uI",
    "neighbourgood": "96zWlHxa9R49qlpyJKO7",
    "nob_hill_run_club": "gaH33LxCrvQo0r1F2Y5M",
    "sf_chess_club": "98UJpsxnnCr8p7cb77hD",
    "sf_supper_club": "eL7Hrq2H8LxUXbEasEGA",
    "touch_grass_walk_club": "3Kd8VzusjiFIN0wx4TVs",
    "web_artists": "DpKsStjnolxJV0zADMiC",
    "wine_club_sf": "kplE3z7o8Vq9N2O4zKlU",
}

# Tracked explore events are only re-checked once they start within this
# many days — a bit past the sync engine's 14-day push window
# (app/sync_engine.py _LOOKAHEAD_DAYS).
_HORIZON_DAYS = 16

_URLS = [
    "https://partiful.com/explore/sf",
    "https://partiful.com/explore/sf?tag=music",
    "https://partiful.com/explore/sf?tag=community",
    "https://partiful.com/explore/sf?tag=arts",
]

_EVENT_URL = "https://partiful.com/e/{event_id}"
_PUBLISHED_EVENTS_API = "https://api.partiful.com/getPublishedEvents"


# ---------------------------------------------------------------------------
# Shared helpers: fetching Partiful's Next.js page data and normalizing raw
# event objects (used both by the city-wide "explore" scraper below and by
# any scraper tracking a specific host's page via fetch_partiful_host_events).
# ---------------------------------------------------------------------------

def _fetch_next_data(url: str) -> dict:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script:
        raise RuntimeError(f"__NEXT_DATA__ not found on Partiful page: {url}")
    return json.loads(script.string)


def _is_san_francisco(raw: dict) -> bool:
    location_info = raw.get("locationInfo") or {}
    if location_info.get("type") == "freeform":
        # No mapsInfo for freeform locations (nothing was picked from Places
        # autocomplete), so fall back to substring-matching the host's raw text.
        return "san francisco" in (location_info.get("value") or "").strip().lower()

    approximate_location = (location_info.get("mapsInfo") or {}).get("approximateLocation", "")
    return approximate_location.strip().lower().startswith("san francisco")


def _extract_location(raw: dict) -> Optional[str]:
    """Build a location string from Partiful's `locationInfo`.

    `type` is "structured" (host picked a place from Places autocomplete —
    address in `displayAddressLines`, venue name in `mapsInfo.name`) or
    "freeform" (host just typed text — the whole thing lives in `value`,
    with no address lines at all).
    """
    location_info = raw.get("locationInfo") or {}
    if location_info.get("type") == "freeform":
        return (location_info.get("value") or "").strip() or None

    venue_name = (location_info.get("mapsInfo") or {}).get("name")
    address = ", ".join(location_info.get("displayAddressLines") or []).strip()
    if venue_name and address:
        return f"{venue_name}, {address}"
    return venue_name or address or None


def _extract_raw(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "description": raw.get("description"),
        "start": raw.get("startDate"),
        "end": raw.get("endDate"),
        "timezone": raw.get("timezone") or DEFAULT_TIMEZONE,
        "location": _extract_location(raw),
        "url": f"https://partiful.com/e/{raw.get('id')}",
    }


def _to_event(raw: dict, source: str, title_prefix: str = "") -> Event:
    start = parse_iso_datetime(raw["start"])
    end = parse_iso_datetime(raw["end"]) if raw.get("end") else None
    return Event(
        name=f"{title_prefix}{raw['title']}",
        start_time=start,
        end_time=end,
        location=raw.get("location"),
        description=raw.get("description"),
        source_url=raw["url"],
        source=source,
    )


# ---------------------------------------------------------------------------
# City-wide "explore" feed (partiful.com/explore/sf) — the "partiful" source.
# ---------------------------------------------------------------------------

def _parse_explore_page(next_data: dict) -> List[dict]:
    page = next_data["props"]["pageProps"]
    raws: List[dict] = []

    for item in page.get("trendingSection", {}).get("items", []):
        if item.get("type") == "event" and _is_san_francisco(item["event"]):
            raws.append(_extract_raw(item["event"]))

    for section in page.get("sections", []):
        for item in section.get("items", []):
            if item.get("type") == "event" and _is_san_francisco(item["event"]):
                raws.append(_extract_raw(item["event"]))

    for item in page.get("feedItems", []):
        if item.get("type") == "event" and _is_san_francisco(item["event"]):
            raws.append(_extract_raw(item["event"]))

    return raws


def _fetch_featured() -> Dict[str, dict]:
    """Every SF event currently featured across the explore pages, by id."""
    featured: Dict[str, dict] = {}
    for url in _URLS:
        try:
            raws = _parse_explore_page(_fetch_next_data(url))
        except Exception as exc:
            logger.warning(f"[{_EXPLORE_SOURCE}] failed to fetch {url}: {exc}")
            continue
        for raw in raws:
            event_id = raw.get("id")
            if not event_id or event_id in featured:
                continue
            if not raw.get("start"):
                logger.warning(f"Skipping event with no start date: {event_id}")
                continue
            featured[event_id] = raw
    return featured


def _recheck_event(event_id: str) -> dict:
    """Refetch a tracked event's page; raise EventGone if it's been deleted,
    cancelled, or unpublished."""
    try:
        next_data = _fetch_next_data(_EVENT_URL.format(event_id=event_id))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise EventGone(event_id) from exc
        raise
    event = next_data["props"]["pageProps"].get("event")
    if not event or event.get("isCancelled") or event.get("cancelledAt") or event.get("status") != "PUBLISHED":
        raise EventGone(event_id)
    raw = _extract_raw(event)
    if not raw.get("start"):
        raise EventGone(event_id)
    return raw


def _fetch_explore_events() -> List[Event]:
    """partiful.com/explore/sf, accumulated across runs.

    The explore pages only show a rotating featured subset, so every SF event
    seen there is remembered (app/tracked_event_store.py) and kept on the
    calendar until it ends, rather than vanishing as soon as Partiful stops
    featuring it. Tracked events no longer featured are re-checked against
    their own event page each run, and dropped if deleted or cancelled.
    """
    raws = collect_explore_events(_EXPLORE_SOURCE, _fetch_featured(), _recheck_event, _HORIZON_DAYS)
    events: List[Event] = []
    for raw in raws:
        try:
            events.append(_to_event(raw, _EXPLORE_SOURCE))
        except Exception as exc:
            logger.warning(f"Skipping malformed event {raw.get('id')!r}: {exc}")
    return events


def fetch_events(source: str = _EXPLORE_SOURCE) -> List[Event]:
    if source == _EXPLORE_SOURCE:
        return _fetch_explore_events()
    if source not in _HOST_USER_IDS:
        raise ValueError(f"Unknown Partiful source {source!r} — add it to _HOST_USER_IDS")
    return fetch_partiful_host_events(_HOST_USER_IDS[source], source)


# ---------------------------------------------------------------------------
# Host/community page (partiful.com/u/<user_id>) — every _HOST_USER_IDS
# source. The listing API returns every published event, so unlike the
# explore feed these need no cross-run tracking.
# ---------------------------------------------------------------------------

def _fetch_published_listing(user_id: str) -> List[dict]:
    resp = requests.post(
        _PUBLISHED_EVENTS_API,
        json={"data": {"params": {"userId": user_id}, "userId": None}},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["result"]["data"]


def _fetch_event_raw(event_id: str) -> Optional[dict]:
    next_data = _fetch_next_data(_EVENT_URL.format(event_id=event_id))
    event = next_data["props"]["pageProps"].get("event")
    return _extract_raw(event) if event else None


def fetch_partiful_host_events(user_id: str, source: str, title_prefix: str = "") -> List[Event]:
    """Fetch published events for a Partiful host/community page (partiful.com/u/<user_id>).

    The listing API returns every published event regardless of date, so
    results are pre-filtered to roughly upcoming ones before fetching each
    event's full detail page (needed for location/description).
    """
    try:
        listing = _fetch_published_listing(user_id)
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch host page: {exc}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    events: List[Event] = []

    for item in listing:
        if item.get("status") != "PUBLISHED":
            continue
        start = item.get("startDate")
        if not start:
            continue
        try:
            if parse_iso_datetime(start) < cutoff:
                continue
        except ValueError:
            logger.warning(f"[{source}] skipping event with unparseable startDate: {start!r}")
            continue

        event_id = item.get("id")
        if not event_id:
            continue

        try:
            raw = _fetch_event_raw(event_id)
        except Exception as exc:
            logger.warning(f"[{source}] failed to fetch event {event_id}: {exc}")
            continue
        if not raw or not raw.get("start"):
            continue

        try:
            events.append(_to_event(raw, source, title_prefix))
        except Exception as exc:
            logger.warning(f"[{source}] skipping malformed event {event_id!r}: {exc}")

    logger.info(f"[{source}] parsed {len(events)} events")
    return events
