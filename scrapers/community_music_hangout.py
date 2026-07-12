from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "Community Music Hangout" Google Calendar.
_CALENDAR_ID = "88c5018286c9ab2d0e27326287e61a2b5d42b3ed4008ba650b81f054f65026dd@group.calendar.google.com"
_DISPLAY_URL = "https://calendar.google.com/calendar/embed?src=88c5018286c9ab2d0e27326287e61a2b5d42b3ed4008ba650b81f054f65026dd%40group.calendar.google.com&ctz=America%2FLos_Angeles"
_TZ = ZoneInfo("America/Los_Angeles")


def fetch_events() -> List[Event]:
    return fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
