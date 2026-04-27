from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, NavigableString, Tag

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "http://www.makeoutroom.com/"
_TZ = ZoneInfo("America/Los_Angeles")


# --- Regex --------------------------------------------------------------------

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

_TIME_RE = re.compile(
    r"(\d{1,2}):?(\d{2})?\s*(am|pm)\s*[-–]\s*(\d{1,2}):?(\d{2})?\s*(am|pm)",
    re.IGNORECASE,
)


# --- Helpers ------------------------------------------------------------------

def _clean(text: str) -> str:
    return (
        text.replace("\u200b", "")  # zero-width space
        .replace("\xa0", " ")
        .replace("~", "")
        .strip()
    )


def _parse_date(date_str: str) -> Optional[datetime]:
    m = _DATE_RE.search(date_str or "")
    if not m:
        return None

    month, day, year = map(int, m.groups())
    return datetime(year, month, day, tzinfo=_TZ)


def _parse_time_range(text: str, base_date: datetime) -> tuple[datetime, Optional[datetime]]:
    m = _TIME_RE.search(text or "")
    if not m:
        return base_date, None

    sh, sm, sap, eh, em, eap = m.groups()

    sh = int(sh)
    sm = int(sm or 0)
    eh = int(eh)
    em = int(em or 0)

    if sap.lower() == "pm" and sh != 12:
        sh += 12
    if sap.lower() == "am" and sh == 12:
        sh = 0

    if eap.lower() == "pm" and eh != 12:
        eh += 12
    if eap.lower() == "am" and eh == 12:
        eh = 0

    start = base_date.replace(hour=sh, minute=sm)
    end = base_date.replace(hour=eh, minute=em)

    # Overnight event
    if end <= start:
        end += timedelta(days=1)

    return start, end


# --- Core Fix: Robust Event Splitting -----------------------------------------

def _split_events_from_content(content: Tag) -> List[str]:
    """
    Split content into events using BOTH:
    - <img> (start of event)
    - <hr>  (separator between events)

    Handles deeply nested messy HTML.
    """
    events: List[List[str]] = []
    current: List[str] = []

    for node in content.descendants:
        if isinstance(node, Tag):
            # --- HARD SPLIT POINTS ---
            if node.name in {"img", "hr"}:
                if current:
                    events.append(current)
                    current = []
                continue

            # Only extract meaningful text containers
            if node.name not in {"div", "p", "span", "strong", "em", "a"}:
                continue

            text = node.get_text(" ", strip=True)

        elif isinstance(node, NavigableString):
            text = str(node).strip()
        else:
            continue

        text = _clean(text)

        # Skip noise
        if not text:
            continue

        current.append(text)

    if current:
        events.append(current)

    # Join + filter junk
    cleaned = []
    for e in events:
        combined = "\n".join(e).strip()

        # Filter tiny fragments / layout junk
        if len(combined) < 25:
            continue

        cleaned.append(combined)

    return cleaned


def _extract_title(lines: List[str]) -> str:
    """
    Extract title from top lines until we hit price/time info.
    """
    title_lines = []

    for line in lines:
        if "$" in line or "FREE" in line.upper() or re.search(r"\d{1,2}:\d{2}", line):
            break
        title_lines.append(line)

    title = " ".join(title_lines).strip()

    return title if title else lines[0]


# --- Core parsing -------------------------------------------------------------

def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for post in soup.find_all("div", class_="blog-post"):
        # --- Header ---
        header = post.find("div", class_="blog-header")
        if not header:
            continue

        anchor = header.find("h2", class_="blog-title")
        if not anchor:
            continue

        link = anchor.find("a")
        if not link:
            continue

        url = link.get("href", "")
        if url.startswith("//"):
            url = "http:" + url

        # --- Date ---
        date_tag = header.find("span", class_="date-text")
        if not date_tag:
            continue

        base_date = _parse_date(date_tag.get_text(strip=True))
        if base_date is None:
            continue

        # --- Content ---
        content = post.find("div", class_="blog-content")
        if not content:
            continue

        chunks = _split_events_from_content(content)

        for chunk in chunks:
            lines = [l.strip() for l in chunk.split("\n") if l.strip()]
            if not lines:
                continue

            name = _extract_title(lines)
            description = chunk

            start, end = _parse_time_range(description, base_date)

            events.append(
                Event(
                    name=name,
                    start_time=start,
                    end_time=end,
                    location="Make-Out Room, San Francisco",
                    description=description,
                    source_url=url,
                    source=_SOURCE,
                    unique_key=Event.build_unique_key(name, start),
                )
            )

    return events


# --- Public API ---------------------------------------------------------------

def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_BASE_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events = _parse_page(html)
    logger.info(f"[{_SOURCE}] fetched {len(events)} events")

    return events