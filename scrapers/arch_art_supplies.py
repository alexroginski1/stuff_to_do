from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://shop.archsupplies.com/pages/workshops"
_ADDRESS = "Arch Art Supplies, 1490 17th St, San Francisco, CA 94107"
_TZ = ZoneInfo("America/Los_Angeles")

_MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\b"
)
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?)\s*(am|pm)?\s*-\s*(\d{1,2}(?::\d{2})?)\s*(am|pm)",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"\bFREE\b|\$\d+(?:\.\d{2})?", re.IGNORECASE)


def _to_24h(hm: str, meridiem: str) -> tuple[int, int]:
    if ":" in hm:
        h_str, m_str = hm.split(":")
        hour, minute = int(h_str), int(m_str)
    else:
        hour, minute = int(hm), 0
    hour = hour % 12
    if meridiem.lower() == "pm":
        hour += 12
    return hour, minute


def _parse_date_line(text: str) -> Optional[tuple[datetime, Optional[datetime]]]:
    month_match = _MONTH_RE.search(text)
    time_match = _TIME_RANGE_RE.search(text)
    if not month_match or not time_match:
        return None

    try:
        month = datetime.strptime(month_match.group(1), "%B").month
    except ValueError:
        return None
    day = int(month_match.group(2))

    start_hm, start_meridiem, end_hm, end_meridiem = time_match.groups()
    # e.g. "12:30-2pm" omits the start meridiem; it shares the end's.
    start_meridiem = start_meridiem or end_meridiem

    now = datetime.now(_TZ)
    year = now.year
    try:
        start_hour, start_minute = _to_24h(start_hm, start_meridiem)
        end_hour, end_minute = _to_24h(end_hm, end_meridiem)
        start = datetime(year, month, day, start_hour, start_minute, tzinfo=_TZ)
    except ValueError:
        return None

    # The site never shows a year, so infer it: if the resulting date is
    # already well in the past, it must mean next year.
    if (start - now).days < -30:
        start = start.replace(year=year + 1)

    end = start.replace(hour=end_hour, minute=end_minute)
    if end <= start:
        end = None

    return start, end


def _cell_lines(td) -> List[str]:
    lines = []
    for child in td.find_all(["p", "div"], recursive=False):
        text = child.get_text(" ", strip=True)
        if text:
            lines.append(text)
    return lines


def _parse_cell(td) -> Optional[Event]:
    lines = _cell_lines(td)

    date_idx = None
    parsed = None
    for i, line in enumerate(lines):
        parsed = _parse_date_line(line)
        if parsed:
            date_idx = i
            break

    if date_idx is None or date_idx == 0:
        return None

    name = lines[date_idx - 1]
    start, end = parsed

    link_el = td.select_one("a[href]")
    url = link_el.get("href") if link_el else _URL

    price_match = _PRICE_RE.search(lines[date_idx])
    description = price_match.group().upper() if price_match else None

    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=_ADDRESS,
        description=description,
        source_url=url,
        source=_SOURCE,
        location_verified=True,
    )


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("div.rte table")
    if not table:
        return []

    events: List[Event] = []
    for td in table.select("td"):
        event = _parse_cell(td)
        if event:
            events.append(event)
    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{_SOURCE}] found {len(events)} events")

    return events
