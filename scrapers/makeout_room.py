from __future__ import annotations

# The Make Out Room's own site (makeoutroom.com) has no calendar of its own
# -- events live on a CalendarWiz-hosted calendar (calendarwiz.com/calendars,
# crd=makeoutroom) that the venue embeds elsewhere. The plain calendar URL
# 302s into a JS "chkbrowser" interstitial that re-navigates via a meta
# refresh (which requests won't follow), but passing jsenabled=0 skips that
# and returns the real month grid directly.
#
# Each event is a `<div data-etimestamp="..." data-event_id="...">` in that
# grid; data-etimestamp is the exact start time as a Unix timestamp, and the
# event's `<a>` text is "Title ~ price ~ 7:00pm - 9:00pm" (the venue's own
# tilde-delimited convention). Title is the first segment; the end time, if
# present, is parsed from the trailing time range.

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_CALENDAR_URL = "https://www.calendarwiz.com/calendars/calendar.php?crd=makeoutroom"
_ADDRESS = "3225 22nd St, San Francisco, CA 94110"
_TZ = ZoneInfo("America/Los_Angeles")

# Current month plus this many ahead.
_MONTHS_AHEAD = 3

_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}):?(\d{2})?\s*(am|pm)\s*[-–]\s*(\d{1,2}):?(\d{2})?\s*(am|pm)",
    re.IGNORECASE,
)


def _month_url(month: int, year: int) -> str:
    return f"{_CALENDAR_URL}&op=cal&month={month}&year={year}&jsenabled=0"


def _end_time(text: str, start: datetime) -> Optional[datetime]:
    m = _TIME_RANGE_RE.search(text)
    if not m:
        return None

    eh, em, eap = int(m.group(4)), int(m.group(5) or 0), m.group(6).lower()
    if eap == "pm" and eh != 12:
        eh += 12
    if eap == "am" and eh == 12:
        eh = 0

    end = start.replace(hour=eh, minute=em)
    if end <= start:
        end += timedelta(days=1)
    return end


def _parse_month(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for cell in soup.select("div[data-event_id]"):
        ts = cell.get("data-etimestamp")
        event_id = cell.get("data-event_id")
        link = cell.select_one(".cw-e-a a")
        if not ts or not event_id or not link:
            continue

        text = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
        if not text:
            continue

        try:
            start = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(_TZ)
        except (ValueError, OSError):
            continue

        name = text.split(" ~ ")[0].strip()

        events.append(
            Event(
                name=name,
                start_time=start,
                end_time=_end_time(text, start),
                location=_ADDRESS,
                description=text,
                source_url=f"https://www.calendarwiz.com/calendars/popup.php?op=view&id={event_id}&crd=makeoutroom",
                source=_SOURCE,
                location_verified=True,
            )
        )

    return events


def fetch_events() -> List[Event]:
    events: List[Event] = []

    today = datetime.now(tz=_TZ)
    month, year = today.month, today.year

    for _ in range(_MONTHS_AHEAD):
        url = _month_url(month, year)
        try:
            html = fetch_html(url)
            events.extend(_parse_month(html))
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch {url}: {exc}")

        month += 1
        if month > 12:
            month = 1
            year += 1

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
