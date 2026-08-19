from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers._mato import fetch_mato_venue_events

_SOURCE = Path(__file__).stem
_HANDLE = "transitcentersf"
_ADDRESS = "425 Mission Street, San Francisco, CA 94105"


def fetch_events() -> List[Event]:
    return fetch_mato_venue_events(_HANDLE, _SOURCE, _ADDRESS)
