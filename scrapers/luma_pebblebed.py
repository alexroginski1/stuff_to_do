from __future__ import annotations

from typing import List

from pathlib import Path

from app.event_model import Event
from scrapers.luma import fetch_page_events

_SOURCE = Path(__file__).stem
URL = "https://luma.com/pebblebedevents"


def fetch_events() -> List[Event]:
    return fetch_page_events(URL, _SOURCE)
