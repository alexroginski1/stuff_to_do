from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.meetup import fetch_meetup_group_events

_SOURCE = Path(__file__).stem
_GROUP_URLNAME = "missionfunruns"
# Runs start/end at a different bar in or near the Mission each week, and
# the venue stays "TBD" until a few days before; until then, place it
# approximately in the Mission rather than leaving it unlocated.
_FALLBACK_LOCATION = "Mission District, San Francisco"


def fetch_events() -> List[Event]:
    events = fetch_meetup_group_events(_GROUP_URLNAME, _SOURCE)
    for event in events:
        if not event.location:
            event.location = _FALLBACK_LOCATION
            event.location_inexact = True
    return events
