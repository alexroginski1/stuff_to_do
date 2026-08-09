from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.heylo import fetch_heylo_events

_SOURCE = Path(__file__).stem
_GROUP_ID = "7b9b7d08-d381-4280-bbc7-612795d40302"
_TITLE_PREFIX = "🏐 "


def fetch_events() -> List[Event]:
    return fetch_heylo_events(_GROUP_ID, _SOURCE, _TITLE_PREFIX)
