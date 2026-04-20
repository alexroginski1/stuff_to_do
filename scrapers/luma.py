from __future__ import annotations

# Luma uses a React SPA. Events are loaded via their API:
# GET https://api.lu.ma/discover/get-paginated-events?pagination_limit=50&city=sf
# Response: {"entries": [{"event": {...}, "api_id": "..."}]}
# Each event has: name, start_at (ISO UTC), end_at, geo_address_json.full_address, url
# Requires: requests (no JS rendering needed — the API is public JSON)

import logging
from typing import List

from app.event_model import Event

logger = logging.getLogger(__name__)

SOURCE = "luma"
URL = "https://lu.ma/sf"


def fetch_events() -> List[Event]:
    logger.warning(f"[{SOURCE}] scraper not yet implemented — returning empty")
    return []
