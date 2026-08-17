from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.heylo import fetch_heylo_events

_SOURCE = Path(__file__).stem
_GROUP_ID = "b30541ef-38c1-40c6-af55-3d100bf5d93d"
_TITLE_PREFIX = "✷ "


def fetch_events() -> List[Event]:
    return fetch_heylo_events(_GROUP_ID, _SOURCE, _TITLE_PREFIX)
