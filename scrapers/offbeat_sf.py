from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://offbeatsf.com/events/list/"
_TZ = ZoneInfo("America/Los_Angeles")

_MIN_PAGE = 1
_MAX_PAGE = 20


# ------------------------
# URL
# ------------------------
def _page_url(page: int) -> str:
    if page == 1:
        return _BASE_URL
    return f"{_BASE_URL}page/{page}/"


# ------------------------
# DATETIME
# ------------------------
def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ------------------------
# PRICE PARSING
# ------------------------
def _extract_price_str(text: str) -> Optional[str]:
    if not text:
        return None

    patterns = [
        r"\bFree\b",
        r"\bDonation\b",
        r"\$\d+(?:\.\d{2})?(?:\s*-\s*\$\d+(?:\.\d{2})?)?",
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(0)

    return None


def _parse_price_value(price_str: str) -> Optional[int]:
    """
    Convert price string → rounded integer dollars

    Examples:
    "Free" -> 0
    "$10" -> 10
    "$10.50" -> 11
    "$10-$20" -> 15
    """
    if not price_str:
        return None

    price_str = price_str.lower()

    if "free" in price_str:
        return 0

    # Extract all numeric values
    nums = re.findall(r"\d+(?:\.\d+)?", price_str)
    if not nums:
        return None

    values = [float(n) for n in nums]

    # If range → average
    if len(values) > 1:
        avg = sum(values) / len(values)
        return round(avg)

    return round(values[0])


def _format_price(price: int) -> str:
    if price == 0:
        return "Free"
    return f"${price}"


# ------------------------
# PARSER
# ------------------------

def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    rows = soup.select("article.tribe-events-calendar-list__event")

    for row in rows:
        # --- TITLE + URL ---
        anchor = row.select_one('a[href*="/event/"]')
        if not anchor:
            continue

        name = anchor.get_text(strip=True)
        url = anchor.get("href")

        # --- TIME ---
        time_tag = row.find("time")
        start = _parse_dt(time_tag.get("datetime")) if time_tag else None

        # --- DESCRIPTION ---
        description = row.get_text(" ", strip=True)

        # --- PRICE (fallback scan) ---
        price_str = _extract_price_str(description)
        price_value = _parse_price_value(price_str) if price_str else None

        if price_value is not None:
            price_clean = _format_price(price_value)
            name = f"{name} ({price_clean})"
            description = f"Price: {price_clean}. {description}"

        events.append(
            Event(
                name=name,
                start_time=start,
                end_time=None,
                location=None,
                description=description,
                source_url=url,
                source=_SOURCE,
                unique_key=Event.build_unique_key(name, start),
            )
        )

    return events


# ------------------------
# FETCH
# ------------------------
def fetch_events() -> List[Event]:
    all_events: List[Event] = []

    for page in range(_MIN_PAGE, _MAX_PAGE + 1):
        url = _page_url(page)

        try:
            html = fetch_html(url)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed page {page}: {exc}")
            continue

        page_events = _parse_page(html)

        if not page_events:
            logger.info(f"[{_SOURCE}] no events on page {page}")
            continue

        all_events.extend(page_events)
        logger.info(f"[{_SOURCE}] page {page}: {len(page_events)} events")

    return all_events