from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "decentered"
_URL = "https://events.decentered.org/v1/events"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_dt(date_str: str, time_obj: dict) -> Optional[datetime]:
    """
    Combines:
      date: "2026-04-20"
      time: {"hour": 18, "minute": 0, "second": 0}
    """
    try:
        return datetime(
            year=int(date_str[:4]),
            month=int(date_str[5:7]),
            day=int(date_str[8:10]),
            hour=time_obj.get("hour", 0),
            minute=time_obj.get("minute", 0),
            second=time_obj.get("second", 0),
            tzinfo=_TZ,
        )
    except Exception:
        return None


def _normalize_cost(cost: Optional[str]) -> Optional[str]:
    if not cost:
        return None
    return cost.strip()


def _parse_events(payload: dict) -> List[Event]:
    events: List[Event] = []
    seen_ids = set()

    for e in payload.get("events", []):
        event_id = e.get("id")
        if not event_id or event_id in seen_ids:
            continue
        seen_ids.add(event_id)

        name = e.get("name")
        date = e.get("date")
        start_obj = e.get("start", {})
        end_obj = e.get("end", {})

        if not name or not date:
            continue

        start_dt = _parse_dt(date, start_obj)
        if not start_dt:
            continue

        end_dt = _parse_dt(date, end_obj)

        location = e.get("address") or e.get("location")

        events.append(
            Event(
                name=name,
                start_time=start_dt,
                end_time=end_dt,
                location=location,
                description=e.get("description"),
                source_url=e.get("link") or _URL,
                source=SOURCE,
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
        logger.warning(f"[{SOURCE}] failed to fetch events: {exc}")
        return []

    events = _parse_events(payload)
    logger.info(f"[{SOURCE}] parsed {len(events)} events")
    return events