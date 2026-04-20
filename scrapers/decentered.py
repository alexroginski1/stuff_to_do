from __future__ import annotations

# Decentered is a Squarespace site.
# URL: https://decentered.org/events
# Events rendered server-side as <article> or <li class="eventlist-event"> blocks
# with JSON-LD <script type="application/ld+json"> per event (startDate, endDate, location, name, url)
# Requires: requests + BeautifulSoup (parse JSON-LD — no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "decentered"
URL = "https://decentered.org/events"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
