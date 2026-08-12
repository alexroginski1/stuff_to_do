from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.meetup import fetch_meetup_group_events

_SOURCE = Path(__file__).stem
_GROUP_URLNAME = "20-somethings-friends-fun-in-sf"


def fetch_events() -> List[Event]:
    return fetch_meetup_group_events(_GROUP_URLNAME, _SOURCE)
