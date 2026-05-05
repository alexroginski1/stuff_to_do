from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from pathlib import Path

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://www.sketchboard.co/schedule"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_date_time(date_str: str, time_str: str) -> Optional[datetime]:
    """
    Combines:
      date: "Sunday, May 3, 2026"
      time: "2:00 PM"
    """
    try:
        clean_time = time_str.replace("\u202f", " ")  # fix narrow space
        dt_str = f"{date_str}, {clean_time}"
        return datetime.strptime(dt_str, "%A, %B %d, %Y, %I:%M %p").replace(tzinfo=_TZ)
    except Exception:
        return None


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for block in soup.select("div.eventlist-column-info"):
        # --- title + url ---
        title_el = block.select_one(".eventlist-title a")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        if url.startswith("/"):
            url = f"https://www.sketchboard.co{url}"

        # --- date ---
        date_el = block.select_one(".event-date")
        if not date_el:
            continue
        date_str = date_el.get_text(strip=True)

        # --- times ---
        start_el = block.select_one(".event-time-localized-start")
        end_el = block.select_one(".event-time-localized-end")

        if not start_el:
            continue

        start = _parse_date_time(date_str, start_el.get_text(strip=True))
        if not start:
            continue

        end: Optional[datetime] = None
        if end_el:
            end = _parse_date_time(date_str, end_el.get_text(strip=True))

        # --- location ---
        loc_el = block.select_one(".eventlist-meta-address")
        location = None
        if loc_el:
            # remove "(map)" text
            location = loc_el.get_text(strip=True)
            location = location.replace("(map)", "").strip()

        events.append(Event(
            name=name,
            start_time=start,
            end_time=end,
            location=location,
            description=None,
            source_url=url,
            source=_SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

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