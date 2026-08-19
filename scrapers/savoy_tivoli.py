from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# The site's "Savoy Tivoli Calendar" widget (calendar.boomte.ch) is itself
# just a synced view of this public Google Calendar, so read it directly.
_CALENDAR_ID = "thesavoytivoli@gmail.com"
_DISPLAY_URL = "https://www.savoytivoli.com/"
_TZ = ZoneInfo("America/Los_Angeles")

# Recurring placeholder listings advertising private-event bookings, not
# actual shows; requested exclusion.
_EXCLUDE_SUBSTRING = "private party"

_DEFAULT_LOCATION = "1434 Grant Ave, San Francisco, CA 94133"


def fetch_events() -> List[Event]:
    events = fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
    filtered: List[Event] = []
    for event in events:
        if _EXCLUDE_SUBSTRING in event.name.lower():
            continue
        if not event.location:
            event.location = _DEFAULT_LOCATION
            event.location_verified = True
        filtered.append(event)
    return filtered
