from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "Moonlit Moves" Google Calendar (The Polish Club Inc., 3040 22nd St).
_CALENDAR_ID = "f3bfcf5b10ff8cb2ba35abba749ccd68bc8347e2d522e6baca32448c9b2695cc@group.calendar.google.com"
_DISPLAY_URL = "https://calendar.google.com/calendar/embed?src=f3bfcf5b10ff8cb2ba35abba749ccd68bc8347e2d522e6baca32448c9b2695cc%40group.calendar.google.com&ctz=America%2FLos_Angeles"
_TZ = ZoneInfo("America/Los_Angeles")


def fetch_events() -> List[Event]:
    return fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
