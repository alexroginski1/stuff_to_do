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
_URL = "https://www.goldensardinesf.com/events"
_ADDRESS = "362 Columbus Ave, San Francisco, CA 94133"
_TZ = ZoneInfo("America/Los_Angeles")

# e.g. "5:30p" or "6pm"
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m?", re.IGNORECASE)


def _parse_time(text: str) -> Optional[tuple[int, int]]:
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "p":
        hour += 12
    return hour, minute


def _parse_date(month_name: str, day_str: str) -> Optional[datetime]:
    try:
        month = datetime.strptime(month_name.strip(), "%B").month
        day = int(day_str.strip())
    except ValueError:
        return None

    now = datetime.now(_TZ)
    year = now.year
    candidate = datetime(year, month, day, tzinfo=_TZ)

    # The site never shows a year, so infer it: if the resulting date is
    # already well in the past, it must mean next year.
    if (candidate - now).days < -30:
        candidate = datetime(year + 1, month, day, tzinfo=_TZ)

    return candidate


def _parse_event(item) -> Optional[Event]:
    title_el = item.select_one("h3.cms-title")
    if not title_el:
        return None
    name = title_el.get_text(strip=True)

    fields = item.select_one(".h-flex-wrap")
    if not fields:
        return None
    children = fields.select(":scope > .h-flex-wrap_child")
    if len(children) < 3:
        return None

    _, date_child, time_child = children[0], children[1], children[2]

    date_parts = date_child.select(".agrandir")
    if len(date_parts) < 2:
        return None
    date_base = _parse_date(date_parts[0].get_text(strip=True), date_parts[1].get_text(strip=True))
    if not date_base:
        return None

    start_text_el = time_child.select_one(".agrandir")
    start_hm = _parse_time(start_text_el.get_text(strip=True)) if start_text_el else None
    if not start_hm:
        return None
    start_time = date_base.replace(hour=start_hm[0], minute=start_hm[1])

    end_time = None
    end_text_el = time_child.select_one(".end-time")
    if end_text_el:
        end_hm = _parse_time(end_text_el.get_text(strip=True))
        if end_hm:
            end_time = date_base.replace(hour=end_hm[0], minute=end_hm[1])
            if end_time <= start_time:
                end_time = None

    desc_el = item.select_one("p.no-margin")
    description = desc_el.get_text(" ", strip=True) if desc_el else None

    return Event(
        name=name,
        start_time=start_time,
        end_time=end_time,
        location=_ADDRESS,
        description=description or None,
        source_url=_URL,
        source=_SOURCE,
        location_verified=True,
    )


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    upcoming = soup.select_one('div.events-upcoming[data-w-tab="Upcoming"]')
    if not upcoming:
        return []

    events = []
    for item in upcoming.select(".cms-item"):
        event = _parse_event(item)
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
