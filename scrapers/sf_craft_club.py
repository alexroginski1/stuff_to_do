from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.luma import fetch_luma_events

_SOURCE = Path(__file__).stem
_URL = "https://api.luma.com/user/profile/events-hosting?user_api_id=usr-Bz2fgNXYkRygsqe&period=future"


def fetch_events() -> List[Event]:
    return fetch_luma_events(_URL, _SOURCE, sf_only=True)
