from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
_CALENDAR_ID = "k5bmnva5i30lo1id9kovrvjc4g@group.calendar.google.com"
_DISPLAY_URL = (
    "https://calendar.google.com/calendar/u/0/embed?ctz=America%2FLos_Angeles"
    "&src=k5bmnva5i30lo1id9kovrvjc4g%40group.calendar.google.com"
)
_TZ = ZoneInfo("America/Los_Angeles")

_DEFAULT_LOCATION = "663 Haight St, San Francisco, CA 94117"
_COMMUNITY_EVENTS_URL = "https://www.wavecollectivespace.com/community-events"


def fetch_events() -> List[Event]:
    events = fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )

    kept: List[Event] = []
    for event in events:
        if "private event" in event.name.lower():
            continue
        if not event.location:
            event.location = _DEFAULT_LOCATION
            event.location_verified = True
        event.description = (
            f"{event.description}\n\n{_COMMUNITY_EVENTS_URL}" if event.description else _COMMUNITY_EVENTS_URL
        )
        kept.append(event)

    return kept
