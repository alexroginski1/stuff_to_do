from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from app.utils import fetch_eventbrite_organizer_events

_SOURCE = Path(__file__).stem
_ORGANIZER_ID = "15114280512"


def fetch_events() -> List[Event]:
    return fetch_eventbrite_organizer_events(_ORGANIZER_ID, _SOURCE)
