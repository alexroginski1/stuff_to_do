from __future__ import annotations

# The Makeout Room uses a static HTML site (or WordPress).
# URL: http://www.makeoutroom.com/
# Events listed as <li> or <div> entries with date strings and show names.
# Parse the event list from the homepage; follow each event link for full details.
# Requires: requests + BeautifulSoup (no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "makeoutroom"
URL = "http://www.makeoutroom.com/"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
