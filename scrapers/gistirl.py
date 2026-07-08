from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests

from pathlib import Path

from app.event_model import Event

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = (
    "https://us-central1-speed-dating-sf.cloudfunctions.net/fetchEventsUnAuth"
    "?lat=37.7958&lng=-122.4203&radiusKm=40.2336"
)
_DISPLAY_URL = "https://app.gistirl.com/"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ)
    except Exception:
        return None


def _is_san_francisco(address: str) -> bool:
    return "san francisco" in address.lower()


def _parse_events(payload: dict) -> List[Event]:
    events: List[Event] = []

    for e in payload.get("data", []):
        if not e.get("isActive") or e.get("isPrivate"):
            continue

        address = e.get("address") or ""
        if not _is_san_francisco(address):
            continue

        name = e.get("name")
        start = _parse_dt(e.get("date"))
        if not name or not start:
            continue

        events.append(Event(
            name=name.strip(),
            start_time=start,
            end_time=None,
            location=e.get("hostname") or address,
            description=e.get("description"),
            source_url=_DISPLAY_URL,
            source=_SOURCE,
        ))

    return events


def fetch_events() -> List[Event]:
    try:
        resp = requests.get(_URL, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch events: {exc}")
        return []

    events = _parse_events(payload)
    logger.info(f"[{_SOURCE}] parsed {len(events)} events")
    return events
