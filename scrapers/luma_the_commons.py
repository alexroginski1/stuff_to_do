from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from scrapers.luma import fetch_luma_events

_SOURCE = Path(__file__).stem
_URL = "https://api.luma.com/calendar/get-items?calendar_api_id=cal-ahTi4ptrN9WCYkg&pagination_limit=20&period=future"
# The Commons doesn't reliably expose a usable address via Luma's geo data
# (often obfuscated down to just "Hayes Valley"), so hardcode its real address
# rather than relying on that.
_ADDRESS = "550 Laguna St, San Francisco"


def fetch_events() -> List[Event]:
    events = fetch_luma_events(_URL, _SOURCE)
    events = [e for e in events if "members only" not in e.name.lower()]
    for event in events:
        event.location = _ADDRESS
        event.location_verified = True
    return events
