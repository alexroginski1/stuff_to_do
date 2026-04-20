from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html, parse_iso_datetime

logger = logging.getLogger(__name__)

SOURCE = "luma"
URL = "https://luma.com/discover"


def _parse_location(geo: Optional[dict]) -> Optional[str]:
    if not geo:
        return None
    return geo.get("full_address") or geo.get("city_state") or geo.get("city")


def _parse_page(next_data: dict) -> List[Event]:
    initial_data = next_data["props"]["pageProps"]["initialData"]
    featured = initial_data.get("featured_place", {})
    entries = featured.get("events", [])

    events: List[Event] = []
    seen: set[str] = set()

    for entry in entries:
        ev = entry.get("event", {})
        name = ev.get("name", "").strip()
        start_raw = ev.get("start_at") or entry.get("start_at")
        if not name or not start_raw:
            continue

        try:
            start_time = parse_iso_datetime(start_raw)
        except Exception:
            continue

        end_raw = ev.get("end_at")
        end_time = parse_iso_datetime(end_raw) if end_raw else None

        slug = ev.get("url", "")
        source_url = f"https://lu.ma/{slug}" if not slug.startswith("http") else slug

        location = _parse_location(ev.get("geo_address_info"))

        api_id = ev.get("api_id") or entry.get("api_id", "")
        if api_id in seen:
            continue
        if api_id:
            seen.add(api_id)

        events.append(Event(
            name=name,
            start_time=start_time,
            end_time=end_time,
            location=location,
            description=None,
            source_url=source_url,
            source=SOURCE,
            unique_key=Event.build_unique_key(name, start_time),
        ))

    logger.info(f"[{SOURCE}] fetched {len(events)} events")
    return events


def fetch_events() -> List[Event]:
    html = fetch_html(URL)
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})

    if not script:
        raise RuntimeError("__NEXT_DATA__ not found on Luma discover page")

    next_data = json.loads(script.string)
    return _parse_page(next_data)
