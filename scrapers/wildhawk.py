from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers._plumpjack_elfsight import fetch_plumpjack_events

_SOURCE = Path(__file__).stem
_CALENDAR_URL = "https://www.wildhawksf.com/happenings"
_LOCATION_FILTER_ID = "wildhawk"
_ADDRESS = "3464 19th St, San Francisco, CA 94110"


def fetch_events() -> List[Event]:
    return fetch_plumpjack_events(
        location_filter_id=_LOCATION_FILTER_ID,
        address=_ADDRESS,
        calendar_url=_CALENDAR_URL,
        source=_SOURCE,
    )
