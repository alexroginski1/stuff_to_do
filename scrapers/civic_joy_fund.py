from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from app.utils import fetch_mobilize_org_events

_SOURCE = Path(__file__).stem
_ORG_SLUG = "civicjoyfund"
# No tag filter: Civic Joy Fund's Mobilize page is entirely volunteering
# (cleanups, park workdays), but not every event carries the "Community
# Service" tag (546) — e.g. Leland Avenue Cleanup and the Buena Vista Park
# volunteering days don't. Their non-volunteering events (night markets,
# block parties) live on their Google Calendar instead and are pulled by
# civic_joy_fund_events.py into SF Community.


def fetch_events() -> List[Event]:
    return fetch_mobilize_org_events(_ORG_SLUG, _SOURCE)
