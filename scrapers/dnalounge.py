from __future__ import annotations

# DNA Lounge has a well-structured events calendar.
# URL: https://www.dnalounge.com/
# Calendar page lists events in structured HTML: <div class="event"> blocks
# Each block has: date header, event title <a href="/calendar/.../">, start time
# Requires: requests + BeautifulSoup (no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "dnalounge"
URL = "https://www.dnalounge.com/"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
