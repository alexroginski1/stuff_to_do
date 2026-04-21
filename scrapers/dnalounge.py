from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

SOURCE = "dnalounge"
_BASE_URL = "https://www.dnalounge.com/calendar/latest.html"
_TZ = ZoneInfo("America/Los_Angeles")

# DNA Lounge always in SF
_LOCATION = "DNA Lounge, San Francisco"

# Example: "Mon Apr 20"
_DATE_RE = re.compile(r"\b([A-Za-z]{3}) ([A-Za-z]{3}) (\d{1,2})\b")


def _parse_date(text: str) -> Optional[datetime]:
    """
    Convert "Mon Apr 20" → datetime with inferred year.
    Strategy: assume current year, adjust if already passed far in future.
    """
    m = _DATE_RE.search(text)
    if not m:
        return None

    _, month_str, day_str = m.groups()

    try:
        month = datetime.strptime(month_str, "%b").month
        day = int(day_str)
    except ValueError:
        return None

    now = datetime.now(_TZ)
    year = now.year

    dt = datetime(year, month, day, tzinfo=_TZ)

    # If it's > ~6 months in the past, assume next year
    if (dt - now).days < -180:
        dt = datetime(year + 1, month, day, tzinfo=_TZ)

    return dt


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for a in soup.find_all("a", class_="thumbox"):
        url = a.get("href", "")
        if not url:
            continue

        # Title + date block
        txt = a.find("div", class_="thumbox_txt")
        if not txt:
            continue

        # Extract title
        b = txt.find("b")
        if not b:
            continue
        name = b.get_text(strip=True)

        # Extract date text (everything in txt minus <b>)
        raw_text = txt.get_text(" ", strip=True)
        start = _parse_date(raw_text)
        if not start:
            continue

        # Description from image alt (best available)
        img = a.find("img")
        description = img.get("alt") if img else None

        events.append(Event(
            name=name,
            start_time=start,
            end_time=None,  # not available
            location=_LOCATION,
            description=description,
            source_url=url if url.startswith("http") else f"https://www.dnalounge.com{url}",
            source=SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_BASE_URL)
    except Exception as exc:
        logger.warning(f"[{SOURCE}] failed to fetch: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{SOURCE}] fetched {len(events)} events")
    return events