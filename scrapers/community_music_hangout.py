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

# Most events on this calendar omit LOCATION. Sunday hangouts are always at
# the public piano near JFK Dr @ Blue Heron Lake Dr in Golden Gate Park
# (37°46'16.4"N 122°28'26.1"W) — a known-correct pin, not a Places-resolvable
# address, so it's hardcoded here and marked verified rather than left for
# Google Places to (fail to) resolve.
_SUNDAY_PIANO_COORDS = "37.771222,-122.473917"

_EXTRA_INFO = (
    "https://goldengatejams.com/\n"
    "We will meet at the public piano on JFK @ Blue Heron Lake Drive."
)


def fetch_events() -> List[Event]:
    events = fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
    for event in events:
        event.description = (
            f"{event.description}\n\n{_EXTRA_INFO}" if event.description else _EXTRA_INFO
        )
        if not event.location and event.start_time.weekday() == 6:
            event.location = _SUNDAY_PIANO_COORDS
            event.location_verified = True
    return events
