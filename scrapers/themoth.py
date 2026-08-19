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
_LISTING_URL = "https://www.themoth.org/tickets/upcoming-events?location=san-francisco-ca"
_TZ = ZoneInfo("America/Los_Angeles")

# Filtering the listing by location still includes nearby cities (e.g.
# Berkeley); only keep cards explicitly tagged as San Francisco.
_SF_CITY_LABEL = "San Francisco, CA"

# "Doors Open: 6:30pm          Stories Begin: 7:30pm" — grabs every clock
# time in the block; the last one is when the show/stories actually start.
_TIME_RE = re.compile(r"\d{1,2}:\d{2}\s*[ap]m", re.I)
_AGE_SUFFIX_RE = re.compile(r"\s*\(\d+\+\)\s*$")


def _parse_show_date(date_text: str, time_text: str) -> Optional[datetime]:
    # date_text: "Tuesday, August 25"; time_text holds the doors/start clock times.
    times = _TIME_RE.findall(time_text)
    if not times:
        return None
    start_clock = times[-1]

    now = datetime.now(_TZ)
    for year in (now.year, now.year + 1):
        try:
            dt = datetime.strptime(f"{date_text} {year} {start_clock}", "%A, %B %d %Y %I:%M%p")
        except ValueError:
            continue
        dt = dt.replace(tzinfo=_TZ)
        if dt >= now:
            return dt
    return None


def _parse_location(soup: BeautifulSoup) -> Optional[str]:
    heading = soup.find("h2", class_="text-lockup__heading", string="Location")
    if not heading:
        return None
    container = heading.find_parent("div", class_="text-lockup")
    if not container:
        return None
    link = container.find("a")
    if not link:
        return None

    parts = [p.strip() for p in link.get_text("|").split("|") if p.strip()]
    if len(parts) < 3:
        return None

    venue = _AGE_SUFFIX_RE.sub("", parts[0]).strip()
    if "San Francisco" not in parts[2]:
        return None

    return ", ".join([venue, parts[1], parts[2]])


def _parse_description(soup: BeautifulSoup) -> Optional[str]:
    blocks = soup.find_all("div", class_="rich-text")
    for block in blocks:
        classes = block.get("class", [])
        if "sub-2x" in classes and "text-pretty" in classes:
            text = block.get_text(" ", strip=True)
            if text and "What is a StorySLAM?" not in text:
                return text
    return None


def _fetch_event(url: str, name: str) -> Optional[Event]:
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch event page {url}: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")

    date_p = soup.find("p", class_="title-4x-tall")
    time_p = date_p.find_next_sibling("p") if date_p else None
    if not date_p or not time_p:
        return None

    start = _parse_show_date(date_p.get_text(strip=True), time_p.get_text(" ", strip=True))
    if not start:
        return None

    location = _parse_location(soup)
    if not location:
        # Detail page doesn't confirm an SF venue after all; skip it.
        return None

    return Event(
        name=name,
        start_time=start,
        end_time=None,
        location=location,
        description=_parse_description(soup),
        source_url=url,
        source=_SOURCE,
        location_verified=True,
    )


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_LISTING_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    soup = BeautifulSoup(html, "html.parser")

    events: List[Event] = []
    for card in soup.find_all("div", class_="link-card"):
        city_span = card.find("span", class_="text-(--text-tertiary)")
        if not city_span or city_span.get_text(strip=True) != _SF_CITY_LABEL:
            continue

        link = card.find("a", attrs={"aria-label": True}, href=True)
        if not link:
            continue

        url = link["href"]
        name = link["aria-label"].strip()
        if not url or not name:
            continue

        event = _fetch_event(url, name)
        if event:
            events.append(event)

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
