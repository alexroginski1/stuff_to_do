from __future__ import annotations

# SF Funcheap is a WordPress site.
# Events are listed at https://sf.funcheap.com/region/san-francisco/
# Each event: div.tanbox.post with span.title.entry-title > a for title/url
# Date/time: div.meta.archive-meta.date-time with data-event-date / data-event-date-end attrs
# Location: last bare <span> (no class) inside the meta div
# Pagination: /page/N/ suffix; page 1 of ~25

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://sf.funcheap.com/region/san-francisco/"
_TZ = ZoneInfo("America/Los_Angeles")
_MAX_PAGES = 8


def _page_url(page: int) -> str:
    if page == 1:
        return _BASE_URL
    return f"{_BASE_URL}page/{page}/"


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)
    except (ValueError, TypeError):
        return None


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for meta in soup.find_all("div", class_=lambda c: c and "archive-meta" in c):
        start_raw = meta.get("data-event-date")
        end_raw = meta.get("data-event-date-end")

        start = _parse_dt(start_raw)
        if start is None:
            continue
        end = _parse_dt(end_raw)
        if end is not None and end < start:
            end += timedelta(days=1)

        # Location is the last bare span (no class attribute) in the meta div
        location: Optional[str] = None
        for span in meta.find_all("span", recursive=False):
            if not span.get("class"):
                location = span.get_text(strip=True) or None

        # Title and URL are in the sibling span.title.entry-title > a
        parent = meta.parent
        title_span = parent.find("span", class_=lambda c: c and "entry-title" in c) if parent else None
        if title_span is None:
            continue
        anchor = title_span.find("a")
        if anchor is None:
            continue
        name = anchor.get_text(strip=True)
        url = anchor.get("href", "")
        if not name or not url:
            continue

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
    all_events: List[Event] = []
    for page in range(1, _MAX_PAGES + 1):
        url = _page_url(page)
        try:
            html = fetch_html(url)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break
        page_events = _parse_page(html)
        if not page_events:
            logger.info(f"[{_SOURCE}] no events on page {page}, stopping")
            break
        all_events.extend(page_events)
        logger.info(f"[{_SOURCE}] page {page}: {len(page_events)} events")

    return all_events
