from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

__SOURCE = Path(__file__).stem
_BASE_URL = "https://roxie.com/calendar/"
_TZ = ZoneInfo("America/Los_Angeles")

_NOW = datetime.now(tz=_TZ)
_YEAR = _NOW.year
_MONTH = _NOW.month


def _parse_time(day: int, time_str: str) -> Optional[datetime]:
    try:
        dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        return dt.replace(year=_YEAR, month=_MONTH, day=day, tzinfo=_TZ)
    except Exception:
        return None


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for td in soup.find_all("td"):
        day_container = td.find("div", class_="calendar-day-item")
        if not day_container:
            continue

        # Skip past days if desired
        if "past-day" in td.get("class", []):
            continue

        # Extract day number
        day_span = day_container.find("span", class_="calendar-day")
        if not day_span:
            continue

        try:
            day = int(day_span.get_text(strip=True))
        except ValueError:
            continue

        # Iterate films
        for film in day_container.find_all("span", class_="film"):
            title_tag = film.find("p", class_="film-title")
            if not title_tag:
                continue

            name = title_tag.get_text(strip=True)

            link_tag = film.find("a")
            url = link_tag.get("href") if link_tag else ""
            if not name or not url:
                continue

            # Each showtime = separate event
            for showtime in film.find_all("span", class_="film-showtime"):
                time_str = showtime.get_text(strip=True)
                start = _parse_time(day, time_str)

                if not start:
                    continue

                events.append(Event(
                    name=name,
                    start_time=start,
                    end_time=None,
                    location="Roxie Theater",
                    description=None,
                    source_url=url,
                    source=_SOURCE,
                    unique_key=Event.build_unique_key(name, start),
                ))

    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_BASE_URL)
    except Exception as exc:
        logger.error(f"[{_SOURCE}] failed to fetch calendar: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{_SOURCE}] fetched {len(events)} events")

    return events