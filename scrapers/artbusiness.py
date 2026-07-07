from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "SF Art Galleries - Openings & Events" Google Calendar
# (embed: https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com).
_CALENDAR_ID = "33alanb@gmail.com"
_DISPLAY_URL = "https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com&ctz=America%2FLos_Angeles"
_TZ = ZoneInfo("America/Los_Angeles")


def fetch_events() -> List[Event]:
    return fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
