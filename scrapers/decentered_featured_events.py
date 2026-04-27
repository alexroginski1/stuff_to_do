from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

SOURCE = "decentered"
_BASE_URL = "https://decentered.org/events"
_TZ = ZoneInfo("America/Los_Angeles")

PRICE_REGEX = re.compile(r"\$\s?\d+(?:\.\d{2})?|\$\s?\d+\s?-\s?\$?\d+")


def _extract_price(text: str) -> Optional[str]:
    match = PRICE_REGEX.search(text)
    return match.group(0) if match else None


def _clean_description(text: Optional[str]) -> Optional[str]:
    if not text:
        return text

    price = _extract_price(text)
    if price:
        return f"{price}\n\n{text}"
    return text


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s).replace(tzinfo=_TZ)
    except Exception:
        return None


def _parse_event_card(card: Tag) -> Optional[Event]:
    """
    Heuristic parser since structure is not stable.
    Adjust once real event markup is confirmed.
    """

    # Title
    title_el = card.find(["h2", "h3"])
    if not title_el:
        return None

    name = title_el.get_text(strip=True)

    # Time
    start: Optional[datetime] = None
    time_el = card.find("time")
    if time_el:
        raw = time_el.get("datetime") or time_el.get_text(strip=True)
        start = _parse_dt(raw)

    # Description
    desc_parts = []
    for p in card.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt:
            desc_parts.append(txt)

    description = "\n\n".join(desc_parts) if desc_parts else None
    description = _clean_description(description)

    # Location (very loose heuristic)
    location = None
    for p in card.find_all("p"):
        txt = p.get_text(strip=True)
        if any(word in txt.lower() for word in ["san francisco", "sf", "street", "ave", "venue"]):
            location = txt
            break

    return Event(
        name=name,
        start_time=start,
        end_time=None,
        location=location,
        description=description,
        source_url=_BASE_URL,
        source=SOURCE,
        unique_key=Event.build_unique_key(name, start),
    )


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    # Try parsing generic "card-like" divs
    for div in soup.find_all("div"):
        event = _parse_event_card(div)
        if event:
            events.append(event)

    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_BASE_URL)
    except Exception as exc:
        logger.warning(f"[{SOURCE}] failed to fetch page: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{SOURCE}] found {len(events)} events")
    return events