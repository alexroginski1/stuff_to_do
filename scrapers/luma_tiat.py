from __future__ import annotations

from typing import List

from app.event_model import Event
from scrapers.luma import fetch_page_events

SOURCE = "tiat"
URL = "https://luma.com/tiat"


def fetch_events() -> List[Event]:
    return fetch_page_events(URL, SOURCE)