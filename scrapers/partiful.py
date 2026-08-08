from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html, parse_iso_datetime
from config.settings import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
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
    approximate_location = (
        raw.get("locationInfo", {}).get("mapsInfo", {}).get("approximateLocation", "")
    )
    return approximate_location.strip().lower().startswith("san francisco")


def _extract_raw(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "description": raw.get("description"),
        "start": raw.get("startDate"),
        "end": raw.get("endDate"),
        "timezone": raw.get("timezone") or DEFAULT_TIMEZONE,
        "location": ", ".join(
            raw.get("locationInfo", {}).get("displayAddressLines", [])
        ).strip() or None,
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
# City-wide "explore" feed (partiful.com/explore/sf) — the default "partiful"
# source, surfacing whatever Partiful itself is currently promoting.
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


def fetch_events() -> List[Event]:
    events: List[Event] = []
    seen_ids: set[str] = set()

    for url in _URLS:
        try:
            raws = _parse_explore_page(_fetch_next_data(url))
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch {url}: {exc}")
            continue

        for raw in raws:
            event_id = raw.get("id")
            if event_id in seen_ids:
                continue
            if event_id:
                seen_ids.add(event_id)
            if not raw.get("start"):
                logger.warning(f"Skipping event with no start date: {raw.get('id')}")
                continue
            try:
                events.append(_to_event(raw, _SOURCE))
            except Exception as exc:
                logger.warning(f"Skipping malformed event {raw.get('id')!r}: {exc}")

    return events


# ---------------------------------------------------------------------------
# Host/community page (partiful.com/u/<user_id>) — reusable by any scraper
# that tracks a specific host's published events, analogous to
# scrapers.heylo.fetch_heylo_events.
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
        if not start or parse_iso_datetime(start) < cutoff:
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
