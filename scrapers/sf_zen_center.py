from __future__ import annotations

# San Francisco Zen Center's City Center calendar is a Drupal Views listing.
# https://www.sfzc.org/city-center-calendar lists events grouped by day, each
# row just a start time + practice-center + title/link (no description, no
# end time). Pagination is `?page=N` (Views infinite-scroll pager, degrades
# fine to a normal query param).
#
# Every event's own page (e.g.
# https://www.sfzc.org/calendar/events/city-center/caregivers-sitting-cc-816)
# has the real data in labeled field divs inside <article class="node
# node--type-event">:
#   - div.field--name-field-practice-center .field__item -> location text,
#     e.g. "City Center"
#   - div.field--name-field-dates .field__item -> "August 16, 2026 / 9:00am -
#     1:00pm" (single day) or "Aug 20, 2026 / 4:00pm - Aug 23, 2026 / 11:00am"
#     (multi-day; note the month is abbreviated in the multi-day form)
#   - div.field--name-field-description .field__item -> write-up text
# So the listing pages are only used to discover event URLs; each URL is then
# fetched individually for the actual fields.

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://www.sfzc.org/city-center-calendar"
_TZ = ZoneInfo("America/Los_Angeles")
_MAX_PAGES = 8

_LOCATION_ADDRESSES = {
    "City Center": "300 Page Street San Francisco, CA 94102",
}


def _page_url(page: int) -> str:
    if page == 0:
        return _BASE_URL
    return f"{_BASE_URL}?page={page}"


def _parse_dates(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    text = text.strip()
    left, _, right = text.partition(" - ")

    left_date_str, sep, left_time_str = left.partition(" / ")
    if not sep:
        return None, None
    try:
        start = dtparser.parse(f"{left_date_str} {left_time_str}").replace(tzinfo=_TZ)
    except (ValueError, OverflowError):
        return None, None

    end: Optional[datetime] = None
    if right:
        end_date_str, sep, end_time_str = right.partition(" / ")
        if not sep:
            end_date_str, end_time_str = left_date_str, right
        try:
            end = dtparser.parse(f"{end_date_str} {end_time_str}").replace(tzinfo=_TZ)
        except (ValueError, OverflowError):
            end = None

    return start, end


def _parse_field(article, field_name: str) -> Optional[str]:
    field = article.select_one(f"div.field--name-{field_name} .field__item")
    return field.get_text(" ", strip=True) if field else None


def _resolve_location(raw: Optional[str]) -> Tuple[Optional[str], bool]:
    if raw and raw in _LOCATION_ADDRESSES:
        return _LOCATION_ADDRESSES[raw], True
    return raw, False


def _fetch_event(url: str) -> Optional[Event]:
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch event page {url}: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.node--type-event")
    if article is None:
        return None

    title_el = soup.select_one("h1.page-title")
    name = title_el.get_text(strip=True) if title_el else None
    if not name:
        return None

    dates_text = _parse_field(article, "field-dates")
    if not dates_text:
        return None
    start, end = _parse_dates(dates_text)
    if start is None:
        return None

    location, verified = _resolve_location(_parse_field(article, "field-practice-center"))
    description = _parse_field(article, "field-description")

    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=location,
        description=description,
        source_url=url,
        source=_SOURCE,
        location_verified=verified,
    )


def _parse_listing_page(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for anchor in soup.select("td.views-field-title a[href]"):
        href = anchor.get("href")
        if href:
            urls.append(href)
    return urls


def fetch_events() -> List[Event]:
    event_urls: List[str] = []
    seen = set()
    for page in range(_MAX_PAGES):
        try:
            html = fetch_html(_page_url(page))
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break
        page_urls = _parse_listing_page(html)
        new_urls = [u for u in page_urls if u not in seen]
        if not new_urls:
            logger.info(f"[{_SOURCE}] no new events on page {page}, stopping")
            break
        seen.update(new_urls)
        event_urls.extend(new_urls)

    events: List[Event] = []
    for url in event_urls:
        event = _fetch_event(url)
        if event:
            events.append(event)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
