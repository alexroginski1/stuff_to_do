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
_URL = "https://www.thesfnook.com/api/events"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_iso_dt(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string into timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(_TZ)
    except Exception:
        return None


def _parse_events(payload: dict) -> List[Event]:
    events: List[Event] = []
    seen_ids = set()

    for e in payload.get("events", []):
        event_id = e.get("id")
        if not event_id or event_id in seen_ids:
            continue
        seen_ids.add(event_id)

        if e.get("publicAccess") == "Private":
            continue

        name = e.get("title")
        start_dt = _parse_iso_dt(e.get("startTime"))

        if not name or not start_dt:
            continue

        events.append(
            Event(
                name=name,
                start_time=start_dt,
                end_time=_parse_iso_dt(e.get("endTime")),
                location=e.get("hostedBy"),  # fallback since no address field
                description=e.get("description"),
                source_url=e.get("link") or _URL,
                source=_SOURCE,
                unique_key=Event.build_unique_key(name, start_dt),
            )
        )

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