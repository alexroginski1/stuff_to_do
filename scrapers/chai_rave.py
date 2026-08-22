from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.event_model import Event
from app.utils import fetch_eventbrite_organizer_events

_SOURCE = Path(__file__).stem
_ORGANIZER_ID = "114748992331"


def _is_san_francisco(location: Optional[str]) -> bool:
    # Chai Rave runs the same series across multiple cities (SF, LA, etc.);
    # only push the SF dates. No location data isn't evidence it's out of
    # area, so let it through rather than silently dropping it.
    return not location or "san francisco" in location.lower()


def fetch_events() -> List[Event]:
    events = fetch_eventbrite_organizer_events(_ORGANIZER_ID, _SOURCE)
    return [e for e in events if _is_san_francisco(e.location)]
