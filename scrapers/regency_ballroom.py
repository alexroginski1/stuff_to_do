from __future__ import annotations

# The Regency Ballroom uses Stellar/DoTheBay platform.
# URL: https://www.theregencyballroom.com/shows/
# Shows listed as structured HTML cards, each with: title, date string, ticket link
# Date format typically: "Friday, May 9, 2025 · 8:00 PM"
# Requires: requests + BeautifulSoup (no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "regency_ballroom"
URL = "https://www.theregencyballroom.com/shows/"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
