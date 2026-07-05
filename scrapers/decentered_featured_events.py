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

_SOURCE = Path(__file__).stem
_BASE_URL = "https://decentered.org/events"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_time_range(date_str: str, time_str: str) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Combines Date + Time like:
    "2026-04-27" + "7:00 pm - 9:00 pm"
    """
    if not date_str:
        return None, None

    try:
        if not time_str:
            start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_TZ)
            return start, None

        parts = time_str.replace("–", "-").split("-")
        start_str = parts[0].strip()
        end_str = parts[1].strip() if len(parts) > 1 else None

        start_dt = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %I:%M %p").replace(tzinfo=_TZ)

        end_dt = None
        if end_str:
            end_dt = datetime.strptime(f"{date_str} {end_str}", "%Y-%m-%d %I:%M %p").replace(tzinfo=_TZ)

        return start_dt, end_dt

    except Exception:
        return None, None


def _extract_next_data(soup: BeautifulSoup) -> Optional[dict]:
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None

    try:
        return json.loads(script.string)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to parse __NEXT_DATA__: {exc}")
        return None


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    data = _extract_next_data(soup)
    if not data:
        logger.info(f"[{_SOURCE}] no __NEXT_DATA__ found")
        return events

    try:
        raw_events = (
            data.get("props", {})
                .get("pageProps", {})
                .get("serverData", {})
                .get("initialUpcomingEvents", [])
        )

        for e in raw_events:
            fields = e.get("fields", {})

            name = fields.get("Name")
            date_str = fields.get("Date")
            time_str = fields.get("Time")
            url = fields.get("External Event Link") or ""
            description = fields.get("Full Description")

            start, end = _parse_time_range(date_str, time_str)

            if not name or not start:
                continue

            # Location is an ID reference → not directly usable
            location = None

            events.append(Event(
                name=name.strip(),
                start_time=start,
                end_time=end,
                location=location,
                description=description,
                source_url=url,
                source=_SOURCE,
            ))

    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to parse events: {exc}")

    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_BASE_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch page: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{_SOURCE}] found {len(events)} events")

    return events
