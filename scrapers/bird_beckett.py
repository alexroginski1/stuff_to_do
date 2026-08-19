from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "Bird & Beckett Events" Google Calendar.
_CALENDAR_ID = "r5o3loovr013c5rftpv75lji18@group.calendar.google.com"
_DISPLAY_URL = "https://calendar.google.com/calendar/u/0/embed?mode=week&src=r5o3loovr013c5rftpv75lji18@group.calendar.google.com&ctz=America/Los_Angeles"
_TZ = ZoneInfo("America/Los_Angeles")

# Most events on the calendar omit LOCATION (they're in-store shows); fall
# back to the shop's own address rather than leaving it for Google Places.
_DEFAULT_LOCATION = "653 Chenery St, San Francisco, CA 94131"


def fetch_events() -> List[Event]:
    events = fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
    for event in events:
        if not event.location:
            event.location = _DEFAULT_LOCATION
            event.location_verified = True
    return events
