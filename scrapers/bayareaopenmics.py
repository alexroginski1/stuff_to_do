from __future__ import annotations

# Bay Area Open Mics (https://bayareaopenmics.com/feed.html) lists recurring
# open mics/jams across the whole Bay Area as a static HTML feed, grouped by
# day into the future (roughly a 3-month rolling window). Each occurrence
# links to a per-event detail page with a full write-up (venue blurb, session
# description, and a "Time/When/MC/.../Where/Website/Last updated" info grid).
#
# Only SF-city events are kept. Like sf_bar_guide.py, each recurring event is
# a standing weekly/monthly slot rather than a one-off — but here the site
# itself has already computed concrete upcoming dates for us, so we take every
# occurrence within the sync engine's lookahead window straight from the feed
# instead of computing recurrence math ourselves. Each event's detail page is
# fetched once and reused across its occurrences.

import logging
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://bayareaopenmics.com/"
_FEED_URL = "https://bayareaopenmics.com/feed.html"
_TZ = ZoneInfo("America/Los_Angeles")
_CITY = "San Francisco"
# Small buffer over the sync engine's 14-day lookahead
# (app/sync_engine.py _LOOKAHEAD_DAYS).
_HORIZON_DAYS = 16

# Info-grid labels to leave out of the description entirely.
_SKIP_LABELS = {"Calendar:"}
# Broken out into its own trailing paragraph (see _build_description).
_LAST_UPDATED_LABEL = "Last updated:"

_TIME_PIECE_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)


def _fetch_utf8(url: str) -> str:
    """The site serves UTF-8 without a charset in its Content-Type header, so
    requests falls back to mis-decoding it as ISO-8859-1 (mangling curly
    quotes, middle dots, etc. into "Â·"-style mojibake). That fallback is a
    lossless byte-for-byte mapping, so re-encoding to latin-1 and decoding as
    UTF-8 recovers the original text."""
    text = fetch_html(url)
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _parse_time_piece(text: str, inherited_meridiem: Optional[str]) -> Optional[time]:
    match = _TIME_PIECE_RE.match(text.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or inherited_meridiem or "").lower()
    if not meridiem or not (1 <= hour <= 12):
        return None
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def _parse_time_range(text: Optional[str]) -> tuple[Optional[time], Optional[time]]:
    """Parses feed/detail time strings like "4-7pm", "4:30-6pm", "7pm", or
    "9pm-1am". A meridiem missing from the start piece is inherited from the
    end piece (as in "4-7pm"). Anything that isn't a recognizable time (e.g.
    "8pm-'till last call") is simply left as None."""
    if not text:
        return None, None
    parts = text.strip().split("-", 1)
    start_part = parts[0].strip()
    end_part = parts[1].strip() if len(parts) > 1 else None

    end_meridiem_match = re.search(r"am|pm", end_part, re.I) if end_part else None
    end_meridiem = end_meridiem_match.group(0).lower() if end_meridiem_match else None

    start_time = _parse_time_piece(start_part, end_meridiem)
    end_time = _parse_time_piece(end_part, None) if end_part else None
    return start_time, end_time


def _build_description(detail_soup: BeautifulSoup) -> Optional[str]:
    section = detail_soup.select_one("section.detail-container")
    if not section:
        return None

    paragraphs = [
        text
        for d in section.select(".venue-description")
        if (text := d.get_text(" ", strip=True))
    ]

    info_lines: List[str] = []
    last_updated: Optional[str] = None
    for item in section.select(".info-item"):
        label_el = item.select_one(".info-label")
        value_el = item.select_one(".info-value")
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True)
        value = value_el.get_text(" ", strip=True)
        if not value or label in _SKIP_LABELS:
            continue
        if label == _LAST_UPDATED_LABEL:
            last_updated = value
            continue
        info_lines.append(f"{label}\n{value}")

    blocks = list(paragraphs)
    if info_lines:
        blocks.append("\n".join(info_lines))
    if last_updated:
        blocks.append(f"{_LAST_UPDATED_LABEL}\n{last_updated}")

    return "\n\n".join(blocks) if blocks else None


def _location_from_where(section: BeautifulSoup, venue: str) -> str:
    where_value = None
    for item in section.select(".info-item"):
        label_el = item.select_one(".info-label")
        if label_el and label_el.get_text(strip=True) == "Where:":
            where_value = item.select_one(".info-value")
            break
    if where_value:
        text = where_value.get_text(" ", strip=True)
        # Strip a trailing " | (415) 555-1234"-style phone number, if any.
        return text.split(" | ")[0].strip()
    return f"{venue}, San Francisco, CA"


def _parse_detail_event(
    detail_url: str, soup: BeautifulSoup, venue: str, occurrence_date: date, feed_time_text: Optional[str]
) -> Optional[Event]:
    section = soup.select_one("section.detail-container")
    if not section:
        return None

    title_el = section.select_one(".venue-title")
    name = title_el.get_text(strip=True) if title_el else None
    if not name:
        return None

    time_text = feed_time_text
    for item in section.select(".info-item"):
        label_el = item.select_one(".info-label")
        if label_el and label_el.get_text(strip=True) == "Time:":
            time_text = item.select_one(".info-value").get_text(strip=True)
            break

    start_time, end_time = _parse_time_range(time_text)
    if start_time is None:
        logger.info(f"[{_SOURCE}] skipping {name!r}: no parseable time ({time_text!r})")
        return None

    start_dt = datetime.combine(occurrence_date, start_time, tzinfo=_TZ)
    end_dt = None
    if end_time is not None:
        end_date = occurrence_date
        if end_time < start_time:
            end_date += timedelta(days=1)
        end_dt = datetime.combine(end_date, end_time, tzinfo=_TZ)

    return Event(
        name=name,
        start_time=start_dt,
        end_time=end_dt,
        location=_location_from_where(section, venue),
        description=_build_description(soup),
        source_url=detail_url,
        source=_SOURCE,
    )


def _sf_occurrences(feed_html: str) -> List[tuple[str, date, str, Optional[str]]]:
    """(detail_url, date, venue, feed time text) for every SF occurrence in
    the feed from today through the lookahead horizon."""
    soup = BeautifulSoup(feed_html, "html.parser")
    today = datetime.now(tz=_TZ).date()
    horizon = today + timedelta(days=_HORIZON_DAYS)
    occurrences: List[tuple[str, date, str, Optional[str]]] = []

    for day_div in soup.select("div.feed-day[data-date]"):
        try:
            occurrence_date = date.fromisoformat(day_div["data-date"])
        except ValueError:
            continue
        if occurrence_date < today or occurrence_date > horizon:
            continue

        for event_div in day_div.select("div.feed-event"):
            city_el = event_div.select_one(".feed-event-city")
            if not city_el or city_el.get_text(strip=True) != _CITY:
                continue

            link_el = event_div.select_one(".feed-event-actions a.feed-event-link")
            href = link_el.get("href") if link_el else None
            if not href:
                continue
            detail_url = urljoin(_BASE_URL, href)

            venue_el = event_div.select_one(".feed-event-venue")
            venue = venue_el.get_text(strip=True) if venue_el else ""
            time_el = event_div.select_one(".feed-event-time")
            time_text = time_el.get_text(strip=True) if time_el else None

            occurrences.append((detail_url, occurrence_date, venue, time_text))

    return occurrences


def fetch_events() -> List[Event]:
    try:
        feed_html = _fetch_utf8(_FEED_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch {_FEED_URL}: {exc}")
        return []

    occurrences = _sf_occurrences(feed_html)

    detail_pages: dict[str, Optional[BeautifulSoup]] = {}
    events: List[Event] = []
    for detail_url, occurrence_date, venue, time_text in occurrences:
        if detail_url not in detail_pages:
            try:
                detail_pages[detail_url] = BeautifulSoup(_fetch_utf8(detail_url), "html.parser")
            except Exception as exc:
                logger.warning(f"[{_SOURCE}] failed to fetch detail page {detail_url}: {exc}")
                detail_pages[detail_url] = None
        soup = detail_pages[detail_url]
        if soup is None:
            continue
        event = _parse_detail_event(detail_url, soup, venue, occurrence_date, time_text)
        if event is not None:
            events.append(event)

    logger.info(
        f"[{_SOURCE}] parsed {len(events)} SF events from {len(occurrences)} occurrences "
        f"across {len(detail_pages)} listings"
    )
    return events
