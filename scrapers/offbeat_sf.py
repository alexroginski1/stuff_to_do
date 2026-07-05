from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional
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
_MAX_PAGE = 15


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
def _parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    try:
        dt_str = f"{date_str} {time_str}"
        return datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p").replace(tzinfo=_TZ)
    except Exception:
        return None


# ------------------------
# PRICE
# ------------------------
def _parse_price(text: str) -> Optional[int]:
    if not text:
        return None

    text = text.lower()

    if "free" in text:
        return 0

    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return None

    values = [float(n) for n in nums]

    if len(values) > 1:
        return round(sum(values) / len(values))

    return round(values[0])


def _format_price(price: int) -> str:
    return "Free" if price == 0 else f"${price}"


# ------------------------
# DESCRIPTION CLEANING
# ------------------------
def _clean_description(desc_tag) -> Optional[str]:
    if not desc_tag:
        return None

    seen = set()
    parts = []

    # collect unique text blocks
    for el in desc_tag.find_all(["p", "span", "div"], recursive=True):
        txt = el.get_text(" ", strip=True)
        if txt and txt not in seen:
            seen.add(txt)
            parts.append(txt)

    if not parts:
        # fallback
        text = desc_tag.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        # remove duplicated halves
        half = len(text) // 2
        if text[:half] == text[half:]:
            text = text[:half]

        return text

    return " ".join(parts)


# ------------------------
# PARSER
# ------------------------
from datetime import timedelta

def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    rows = soup.select("article.tribe-events-calendar-list__event")

    for row in rows:
        # ------------------------
        # TITLE + URL
        # ------------------------
        anchor = row.select_one("a.tribe-events-calendar-list__event-title-link")
        if not anchor:
            continue

        name = anchor.get_text(strip=True)
        url = anchor.get("href")

        # ------------------------
        # TIME (FIXED)
        # ------------------------
        time_tag = row.select_one("time.tribe-events-calendar-list__event-datetime")

        start = None
        end = None

        if time_tag:
            date_str = time_tag.get("datetime")

            start_span = time_tag.select_one(".tribe-event-date-start")
            end_span = time_tag.select_one(".tribe-event-time")

            # --- START ---
            if date_str and start_span:
                start_text = start_span.get_text(strip=True)

                if "@" in start_text:
                    start_text = start_text.split("@")[-1].strip()

                start = _parse_datetime(date_str, start_text)

            # --- END ---
            if date_str and end_span:
                end_text = end_span.get_text(strip=True)
                end = _parse_datetime(date_str, end_text)

            # 🔑 HANDLE OVERNIGHT EVENTS
            if start and end and end <= start:
                end = end + timedelta(days=1)

        # ------------------------
        # SAFETY GUARDS (CRITICAL)
        # ------------------------
        if not start:
            continue  # skip invalid events

        if end and end <= start:
            end = None  # prevent Google Calendar error

        # Optional: default duration if missing end
        if start and not end:
            end = start + timedelta(hours=2)

        # ------------------------
        # LOCATION (FIXED)
        # ------------------------
        address_tag = row.select_one("address.tribe-events-calendar-list__event-venue")

        location = None

        if address_tag:
            venue_name = address_tag.select_one(
                ".tribe-events-calendar-list__event-venue-title"
            )
            venue_addr = address_tag.select_one(
                ".tribe-events-calendar-list__event-venue-address"
            )

            parts = []

            if venue_name:
                parts.append(venue_name.get_text(strip=True))

            if venue_addr:
                parts.append(venue_addr.get_text(strip=True))

            if parts:
                location = ", ".join(parts)

        # ------------------------
        # DESCRIPTION (DEDUPED)
        # ------------------------
        desc_tag = row.select_one("div.tribe-events-calendar-list__event-description")
        description = _clean_description(desc_tag)

        # ------------------------
        # PRICE
        # ------------------------
        price_tag = row.select_one("span.tribe-events-c-small-cta__price")

        price_value = None
        if price_tag:
            price_value = _parse_price(price_tag.get_text(strip=True))

        # ------------------------
        # MUTATE TITLE + DESCRIPTION
        # ------------------------
        if price_value is not None:
            price_clean = _format_price(price_value)

            name = f"{name} ({price_clean})"

            # if description:
            #     description = f"Price: {price_clean}. {description}"
            # else:
            #     description = f"Price: {price_clean}"

        # ------------------------
        # BUILD EVENT
        # ------------------------
        events.append(
            Event(
                name=name,
                start_time=start,
                end_time=end,
                location=location,
                description=description,
                source_url=url,
                source=_SOURCE,
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
