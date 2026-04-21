from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "sfjazz"
BASE_URL = "https://www.sfjazz.org/ace-api/events/"
TZ = ZoneInfo("America/Los_Angeles")


def _build_url(start: datetime, end: datetime) -> str:
    return (
        f"{BASE_URL}"
        f"?startDate={start.strftime('%Y-%m-%d')}"
        f"&endDate={end.strftime('%Y-%m-%d')}"
    )


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Handles both timezone-aware and naive ISO strings
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except Exception:
        return None


def _parse_events(data: list[dict]) -> List[Event]:
    events: List[Event] = []

    for e in data:
        name = e.get("name")
        if not name:
            continue

        start = _parse_dt(e.get("eventDate"))
        if start is None:
            continue

        location = e.get("location") or "SFJAZZ Center"

        # Prefer detail page if available
        detail_url = e.get("viewDetailCtaUrl") or e.get("buyTicketCtaUrl") or ""
        if detail_url and detail_url.startswith("/"):
            detail_url = f"https://www.sfjazz.org{detail_url}"

        description = e.get("synopsis") or None

        events.append(Event(
            name=name,
            start_time=start,
            end_time=None,
            location=location,
            description=description,
            source_url=detail_url,
            source=SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return events


def fetch_events() -> List[Event]:
    today = datetime.now(TZ)
    end = today + timedelta(days=90)

    url = _build_url(today, end)
    logger.info(f"[{SOURCE}] fetching {url}")

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error(f"[{SOURCE}] fetch failed: {exc}")
        return []

    events = _parse_events(data)
    logger.info(f"[{SOURCE}] fetched {len(events)} events")

    return events