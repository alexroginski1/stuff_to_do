from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
_CALENDAR_ID = "admin@sunsetmercantilesf.com"
_DISPLAY_URL = (
    "https://calendar.google.com/calendar/embed?src=admin%40sunsetmercantilesf.com"
    "&ctz=America%2FLos_Angeles"
)
_TZ = ZoneInfo("America/Los_Angeles")

_CALENDAR_PAGE_URL = "https://sunsetmercantilesf.com/calendar-pg/"


def fetch_events() -> List[Event]:
    events = fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )

    for event in events:
        event.description = (
            f"{event.description}\n\n{_CALENDAR_PAGE_URL}" if event.description else _CALENDAR_PAGE_URL
        )

    return events
