from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

SOURCE = "mannys"
BASE_URL = "https://welcometomannys.com/events"
TZ = ZoneInfo("America/Los_Angeles")


def _parse_datetime(raw: str) -> Optional[datetime]:
    """
    Manny's HTML does not provide a strict datetime format.
    This tries a few common patterns and falls back safely.
    """
    if not raw:
        return None

    raw = raw.strip()

    # Try a few likely formats
    formats = [
        "%B %d, %Y %I:%M %p",   # April 20, 2026 7:00 PM
        "%b %d, %Y %I:%M %p",   # Apr 20, 2026 7:00 PM
        "%B %d %I:%M %p",       # April 20 7:00 PM
        "%b %d %I:%M %p",       # Apr 20 7:00 PM
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)

            # If year missing, assume current year
            if "%Y" not in fmt:
                dt = dt.replace(year=datetime.now().year)

            return dt.replace(tzinfo=TZ)
        except Exception:
            continue

    logger.warning("Could not parse datetime: %s", raw)
    return None


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    # Manny's uses card-based layout
    for card in soup.select(".event-card"):
        try:
            # --- TITLE ---
            title_el = card.select_one("h3")
            if not title_el:
                continue

            name = title_el.get_text(strip=True)

            # --- DATE / TIME ---
            # Usually stored in h4 (can vary)
            meta_el = card.select_one("h4")
            raw_datetime = meta_el.get_text(strip=True) if meta_el else ""

            start_time = _parse_datetime(raw_datetime)

            # --- URL ---
            link_el = card.select_one("a")
            url = None
            if link_el and link_el.get("href"):
                url = urljoin(BASE_URL, link_el.get("href"))

            # --- DESCRIPTION ---
            # Manny's cards don't have a clean description field,
            # so we reuse the meta text if needed
            description = raw_datetime or None

            # --- FALLBACK TIME ---
            if not start_time:
                start_time = datetime.now(TZ)

            events.append(Event(
                name=name,
                start_time=start_time,
                end_time=None,
                location="Manny's",
                description=description,
                source_url=url,
                source=SOURCE,
                unique_key=Event.build_unique_key(name, start_time),
            ))

        except Exception:
            logger.exception("Failed parsing event card")

    return events


def fetch_events() -> List[Event]:
    html = fetch_html(BASE_URL)
    return _parse_page(html)