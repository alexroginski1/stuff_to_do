from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.heylo import fetch_heylo_events

_SOURCE = Path(__file__).stem
_GROUP_ID = "75ea182e-9df2-4b4d-bc78-a2e299384993"
_TITLE_PREFIX = "🏃 "


def fetch_events() -> List[Event]:
    return fetch_heylo_events(_GROUP_ID, _SOURCE, _TITLE_PREFIX)
