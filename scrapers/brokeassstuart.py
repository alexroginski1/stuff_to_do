from __future__ import annotations

# Broke Ass Stuart events are on DoTheBay (Stellar platform).
# URL: https://brokeassstuart.dothebay.com/
# Events load via XHR: GET https://brokeassstuart.dothebay.com/api/events?page=1
# Response is JSON with {"data": [{"id", "name", "starts_at", "ends_at", "venue": {...}, "url"}]}
# Requires: requests (JSON API — no JS rendering needed)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "brokeassstuart"
URL = "https://brokeassstuart.dothebay.com/"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
