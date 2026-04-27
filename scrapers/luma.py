from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

__SOURCE = Path(__file__).stem
_BASE_URL = "https://luma.com/sf"
_TZ = ZoneInfo("America/Los_Angeles")


def fetch_page_events(url: str, source: str) -> List[Event]:
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{source}] fetch failed: {exc}")
        return []

    try:
        data = _extract_json(html)
        events = _parse_events(data)

        # override source + fix URLs if needed
        for e in events:
            e.source = source

        logger.info(f"[{source}] parsed {len(events)} events")
        return events

    except Exception as exc:
        logger.exception(f"[{source}] parse failed: {exc}")
        return []
        
def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # ISO format from Luma
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ)
    except Exception:
        return None


def _extract_json(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        raise ValueError("Missing __NEXT_DATA__")

    return json.loads(script.string)


def _extract_events(data: dict) -> List[dict]:
    """
    Luma nests events deeply. We recursively search for dicts containing 'event'.
    """
    events = []

    def walk(obj):
        if isinstance(obj, dict):
            if "event" in obj and isinstance(obj["event"], dict):
                events.append(obj["event"])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return events


def _parse_events(data: dict) -> List[Event]:
    raw_events = _extract_events(data)
    results: List[Event] = []

    for ev in raw_events:
        name = ev.get("name")
        url_slug = ev.get("url")
        start = _parse_dt(ev.get("start_at"))
        end = _parse_dt(ev.get("end_at"))

        if not name or not start:
            continue

        # Build full URL
        url = f"https://luma.com/{url_slug}" if url_slug else ""

        # Location (best available)
        location = None
        geo = ev.get("geo_address_info") or {}
        if isinstance(geo, dict):
            location = geo.get("sublocality") or geo.get("city")

        results.append(Event(
            name=name,
            start_time=start,
            end_time=end,
            location=location,
            description=None,
            source_url=url,
            source=_SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return results


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_BASE_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] fetch failed: {exc}")
        return []

    try:
        data = _extract_json(html)
        events = _parse_events(data)
        logger.info(f"[{_SOURCE}] parsed {len(events)} events")
        return events
    except Exception as exc:
        logger.exception(f"[{_SOURCE}] parse failed: {exc}")
        return []