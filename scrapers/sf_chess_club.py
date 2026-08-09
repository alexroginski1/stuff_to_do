from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.partiful import fetch_partiful_host_events

_SOURCE = Path(__file__).stem
_USER_ID = "98UJpsxnnCr8p7cb77hD"


def fetch_events() -> List[Event]:
    return fetch_partiful_host_events(_USER_ID, _SOURCE)
