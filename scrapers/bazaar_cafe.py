from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._eventon import fetch_eventon_events

_SOURCE = Path(__file__).stem
_URL = "https://bazaarcafe.com/calendar/"
# Every event is at the cafe itself; its EventON listings have no venue set.
_ADDRESS = "5927 California St, San Francisco, CA 94121"


def fetch_events() -> List[Event]:
    return fetch_eventon_events(_URL, _SOURCE, ZoneInfo("America/Los_Angeles"), location=_ADDRESS)
