from __future__ import annotations

# The Faight is a Squarespace site.
# URL: https://www.thefaight.com/events
# Events rendered as <article class="eventlist-event"> blocks with JSON-LD per event
# Fields available: name, startDate, endDate, location, url
# Requires: requests + BeautifulSoup (parse JSON-LD — no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "the_faight"
URL = "https://www.thefaight.com/events"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
