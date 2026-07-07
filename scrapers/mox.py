from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "Mox Events" Google Calendar (moxsf.com/events).
_CALENDAR_ID = "6395b6c6ab85cf5ff3b6a1e59bc218ec592b74bfebf94821158bcf7e56c23ab1@group.calendar.google.com"
_DISPLAY_URL = "https://moxsf.com/events"
_TZ = ZoneInfo("America/Los_Angeles")


def fetch_events() -> List[Event]:
    return fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
