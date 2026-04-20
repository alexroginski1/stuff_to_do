from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "luma"
API_URL = "https://api.lu.ma/discover/get-paginated-events"


def _parse_dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _make_key(name: str, start_time: datetime) -> str:
    raw = f"{SOURCE}:{name}:{start_time.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def fetch_events() -> List[Event]:
    params = {"pagination_limit": 50, "city": "sf"}
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error(f"[{SOURCE}] fetch failed: {exc}")
        return []

    entries = data.get("entries", [])
    events: List[Event] = []
    for entry in entries:
        ev = entry.get("event", {})
        name = ev.get("name", "").strip()
        start_time = _parse_dt(ev.get("start_at"))
        if not name or not start_time:
            continue

        end_time = _parse_dt(ev.get("end_at"))
        geo = ev.get("geo_address_info") or ev.get("geo_address_json") or {}
        location = geo.get("full_address") or geo.get("address")
        slug = ev.get("url") or ev.get("api_id", "")
        source_url = f"https://lu.ma/{slug}" if not slug.startswith("http") else slug

        events.append(Event(
            name=name,
            start_time=start_time,
            end_time=end_time,
            location=location,
            description=None,
            source_url=source_url,
            source=SOURCE,
            unique_key=_make_key(name, start_time),
        ))

    logger.info(f"[{SOURCE}] fetched {len(events)} events")
    return events
