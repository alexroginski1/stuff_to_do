from __future__ import annotations

# Great American Music Hall (GAMH) uses the Stellar/NSI platform.
# URL: https://gamh.com/calendar/
# Events listed as structured HTML: each show is a <div class="event-item"> or similar
# with title, date, support acts, ticket link
# Requires: requests + BeautifulSoup (no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "great_american_music_hall"
URL = "https://gamh.com/calendar/"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
