from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from app.utils import fetch_squarespace_events

_SOURCE = Path(__file__).stem
_URL = "https://medicinefornightmares.com/events"


def fetch_events() -> List[Event]:
    return fetch_squarespace_events(_URL, _SOURCE)
