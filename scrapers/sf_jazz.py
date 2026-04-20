from __future__ import annotations

# SF Jazz calendar uses a parameterised URL:
# https://www.sfjazz.org/calendar?date=YYYY-MM-DD&layout=A
# Always use today's date or the nearest upcoming date for `date`.
# Events rendered server-side as <article> blocks or in a JSON payload.
# Strategy: fetch with today's date, then paginate forward if a "next page" link exists.
# Requires: requests + BeautifulSoup (no JS rendering needed for the initial load)

import logging
from datetime import date
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "sf_jazz"
BASE_URL = "https://www.sfjazz.org/calendar"


def _url_for_date(d: date) -> str:
    return f"{BASE_URL}?date={d.isoformat()}&layout=A"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
