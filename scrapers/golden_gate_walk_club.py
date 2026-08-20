from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.partiful import fetch_partiful_host_events

_SOURCE = Path(__file__).stem
_USER_ID = "Uqyv9rLfCdfoExUq88h9"


def fetch_events() -> List[Event]:
    return fetch_partiful_host_events(_USER_ID, _SOURCE)
