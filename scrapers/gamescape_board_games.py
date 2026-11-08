from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "GAMESCAPE EVENTS CALENDAR" Google Calendar.
_CALENDAR_ID = "uppeou70069gepba3iggthbrv4@group.calendar.google.com"
_DISPLAY_URL = "https://calendar.google.com/calendar/u/0/r?cid=uppeou70069gepba3iggthbrv4@group.calendar.google.com"
_TZ = ZoneInfo("America/Los_Angeles")

# Always the store's address, even for the occasional off-site listing.
_ADDRESS = "333 Divisadero St, San Francisco, CA 94117"


def fetch_events() -> List[Event]:
    events = fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
        # Most events (game nights, leagues) are weekly recurring series.
        expand_recurring=True,
        keep_links=True,
    )
    for event in events:
        event.location = _ADDRESS
        event.location_verified = True
    return events
