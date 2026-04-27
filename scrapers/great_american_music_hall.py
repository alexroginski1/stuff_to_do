from __future__ import annotations

import logging
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

__SOURCE = Path(__file__).stem
BASE_URL = "https://gamh.com/calendar/"
TZ = ZoneInfo("America/Los_Angeles")


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for event in soup.select(".seetickets-list-event-container"):
        # Title + URL
        title_el = event.select_one(".event-title a")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        url = title_el.get("href")

        # Skip private events if desired
        if name.strip().upper() == "PRIVATE EVENT":
            continue

        # Date (e.g. "Wed Apr 22")
        date_el = event.select_one(".event-date")
        # Prefer showtime over doortime
        time_el = event.select_one(".see-showtime") or event.select_one(".see-doortime")

        start = None
        date_str = ""
        time_str = ""
        try:
            if date_el:
                date_str = date_el.get_text(strip=True)
                time_str = time_el.get_text(strip=True) if time_el else "8:00PM"
                dt_str = f"{date_str} {time_str} {datetime.now().year}"
                start = datetime.strptime(dt_str, "%a %b %d %I:%M%p %Y")
                start = start.replace(tzinfo=TZ)
        except Exception:
            pass

        if start is None:
            logger.warning("Could not parse datetime: %r — %r %r", name, date_str, time_str)
            continue

        # Optional description (supporting artists)
        desc_el = event.select_one(".supporting-talent")
        description = desc_el.get_text(strip=True) if desc_el else None

        events.append(Event(
            name=name,
            start_time=start,
            end_time=None,
            location="Great American Music Hall",
            description=description,
            source_url=url,
            source=_SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return events


def fetch_events() -> List[Event]:
    html = fetch_html(BASE_URL)
    return _parse_page(html)