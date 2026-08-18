from __future__ import annotations

from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from scrapers._google_calendar import fetch_google_calendar_events

_SOURCE = Path(__file__).stem
# Public "Flax: Art & Design" Google Calendar.
_CALENDAR_ID = "s3ledaqc4l247co5se720laaig@group.calendar.google.com"
_DISPLAY_URL = "https://flaxart.com/workshops-events/?srsltid=AfmBOooYfLsyvCosDkqgH2sP92_eUxOztus_wk68Wy-RaVG6U1l6S3zv"
_TZ = ZoneInfo("America/Los_Angeles")


def fetch_events() -> List[Event]:
    return fetch_google_calendar_events(
        calendar_id=_CALENDAR_ID,
        source=_SOURCE,
        tz=_TZ,
        display_url=_DISPLAY_URL,
    )
