from __future__ import annotations

# SF Funcheap is a WordPress site.
# Events are listed at https://sf.funcheap.com/region/san-francisco/
# Each event card: <article class="event"> with <h2><a href="..."> for title/url
# Date: <abbr class="dtstart" title="ISO-datetime"> inside .event-info
# Location: <span class="location"> or <abbr class="location">
# Requires: requests + BeautifulSoup (no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "funcheap"
URL = "https://sf.funcheap.com/region/san-francisco/"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
