from __future__ import annotations

import logging
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

SOURCE = "gamh"
BASE_URL = "https://gamh.com/calendar/"
TZ = ZoneInfo("America/Los_Angeles")


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for event in soup.select(".elementor-post, article"):
        title_el = event.select_one("h2 a, h3 a")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        url = title_el.get("href")

        date_el = event.select_one("time")
        start = None
        if date_el and date_el.get("datetime"):
            try:
                start = datetime.fromisoformat(date_el["datetime"]).astimezone(TZ)
            except Exception:
                pass

        events.append(Event(
            name=name,
            start_time=start or datetime.now(TZ),
            end_time=None,
            location="Great American Music Hall",
            description=None,
            source_url=url,
            source=SOURCE,
            unique_key=Event.build_unique_key(name, start or datetime.now(TZ)),
        ))

    return events


def fetch_events() -> List[Event]:
    html = fetch_html(BASE_URL)
    return _parse_page(html)