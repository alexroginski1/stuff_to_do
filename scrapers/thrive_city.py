from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from app.utils import fetch_eventbrite_organizer_events

_SOURCE = Path(__file__).stem
# https://www.eventbrite.com/o/thrive-city-36308481623 — the plaza outside
# Chase Center: outdoor movies, live-music lunches, fitness classes, kids'
# music classes.
_ORGANIZER_ID = "36308481623"


def fetch_events() -> List[Event]:
    return fetch_eventbrite_organizer_events(_ORGANIZER_ID, _SOURCE)
