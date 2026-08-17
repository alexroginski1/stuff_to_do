from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.heylo import fetch_heylo_events

_SOURCE = Path(__file__).stem
_GROUP_ID = "eba0b87a-f4ca-4ff2-bdfb-0d6b4729eb84"
_TITLE_PREFIX = "🏃 RUN: "


def fetch_events() -> List[Event]:
    return fetch_heylo_events(_GROUP_ID, _SOURCE, _TITLE_PREFIX)
