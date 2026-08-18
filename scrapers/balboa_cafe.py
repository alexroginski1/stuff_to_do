from __future__ import annotations

# Balboa Cafe's calendar page (https://www.balboacafesf.com/calendar) has no
# server-rendered event content — it embeds a shared "PlumpJack Group
# Calendar" Elfsight widget (app id 4180195a-cc16-4edc-a68e-4a973181da13)
# listing events across every PlumpJack Group venue, filtered client-side to
# this one via `data-elfsight-app-filter-venue="balboa-cafe"`.
#
# Elfsight's boot endpoint (used by the widget itself on page load) returns
# the widget's full config as JSON, including every event's raw recurrence
# rule rather than expanded dates — a weekly happy hour is one record with
# `repeatPeriod: "weeklyOn"` and a weekday code, not one record per future
# Tuesday. So this scraper filters to Balboa Cafe's location id and computes
# each event's next occurrence itself.

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_CALENDAR_URL = "https://www.balboacafesf.com/calendar"
_WIDGET_ID = "4180195a-cc16-4edc-a68e-4a973181da13"
_BOOT_URL = (
    "https://core.service.elfsight.com/p/boot/"
    f"?page=https%3A%2F%2Fwww.balboacafesf.com%2Fcalendar&w={_WIDGET_ID}"
)
_LOCATION_FILTER_ID = "balboa-cafe"
_ADDRESS = "3199 Fillmore St, San Francisco, CA 94123"
_TZ = ZoneInfo("America/Los_Angeles")

_WEEKDAY_CODES = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}

# How far out to search for a next occurrence before giving up (guards
# against an infinite loop if every candidate date is skipped).
_MAX_LOOKAHEAD_WEEKS = 52
_MAX_LOOKAHEAD_YEARS = 5


def _html_to_text(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    return text or None


def _parse_dt(spec: Optional[dict]) -> Optional[datetime]:
    if not spec:
        return None
    try:
        d = date.fromisoformat(spec["date"])
        hour, minute = (int(p) for p in spec["time"].split(":"))
    except (KeyError, ValueError, TypeError):
        return None
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=_TZ)


def _skip_dates(event: dict) -> set[date]:
    skipped = set()
    for exc in event.get("exceptions") or []:
        if exc.get("type") != "skip":
            continue
        raw = exc.get("originalDate")
        if raw is None:
            continue
        try:
            skipped.add(datetime.fromtimestamp(raw / 1000, tz=_TZ).date())
        except (TypeError, ValueError, OSError):
            continue
    return skipped


def _still_relevant(start: date, duration: Optional[timedelta], today: date) -> bool:
    """True if this occurrence hasn't fully finished as of today (day
    granularity) — covers both upcoming events and multi-day events (e.g. a
    holiday pop-up) that are already underway."""
    end = start + duration if duration else None
    return (end or start) >= today


def _next_weekly_start(
    start: date, weekday_codes: List[str], interval: int, skip: set[date], today: date
) -> Optional[date]:
    weekdays = {_WEEKDAY_CODES[c] for c in weekday_codes if c in _WEEKDAY_CODES}
    if not weekdays:
        return None
    interval = max(interval, 1)

    candidate = min(start, today)
    for _ in range(_MAX_LOOKAHEAD_WEEKS * 7 + 7):
        if candidate >= today and candidate.weekday() in weekdays:
            weeks_since_start = (candidate - start).days // 7
            if weeks_since_start % interval == 0 and candidate not in skip:
                return candidate
        candidate += timedelta(days=1)
    return None


def _next_annual_start(
    start: date, duration: Optional[timedelta], skip: set[date], today: date
) -> Optional[date]:
    for year_offset in range(-1, _MAX_LOOKAHEAD_YEARS):
        year = today.year + year_offset
        try:
            candidate = start.replace(year=year)
        except ValueError:  # Feb 29 in a non-leap year
            continue
        if candidate in skip:
            continue
        if _still_relevant(candidate, duration, today):
            return candidate
    return None


def _occurrence(event: dict, today: date) -> Optional[tuple[datetime, Optional[datetime]]]:
    start = _parse_dt(event.get("start"))
    end = _parse_dt(event.get("end"))
    if not start:
        return None
    duration = (end - start) if end else None
    skip = _skip_dates(event)

    period = event.get("repeatPeriod")
    if period == "noRepeat" or period is None:
        occurrence_start = start.date() if _still_relevant(start.date(), duration, today) else None
    elif period == "weeklyOn":
        occurrence_start = _next_weekly_start(
            start.date(), event.get("repeatWeeklyOnDays") or [], event.get("repeatInterval") or 1, skip, today
        )
    elif period == "annuallyOn":
        occurrence_start = _next_annual_start(start.date(), duration, skip, today)
    else:
        logger.warning(f"[{_SOURCE}] unsupported repeatPeriod {period!r} for {event.get('name')!r}, skipping")
        return None

    if occurrence_start is None:
        return None

    occurrence_start_dt = datetime.combine(occurrence_start, start.time(), tzinfo=_TZ)
    occurrence_end_dt = occurrence_start_dt + duration if duration else None
    return occurrence_start_dt, occurrence_end_dt


def _parse_event(event: dict, today: date) -> Optional[Event]:
    name = event.get("name")
    if not name:
        return None

    occurrence = _occurrence(event, today)
    if not occurrence:
        return None
    start_time, end_time = occurrence

    return Event(
        name=name.strip(),
        start_time=start_time,
        end_time=end_time,
        location=_ADDRESS,
        description=_html_to_text(event.get("description")),
        source_url=_CALENDAR_URL,
        source=_SOURCE,
        location_verified=True,
    )


def _extract_events(boot_json: dict) -> List[dict]:
    try:
        settings = boot_json["data"]["widgets"][_WIDGET_ID]["data"]["settings"]
    except (KeyError, TypeError):
        return []

    location_id = next(
        (loc.get("id") for loc in settings.get("locations", []) if loc.get("filterID") == _LOCATION_FILTER_ID),
        None,
    )
    if not location_id:
        return []

    return [e for e in settings.get("events", []) if location_id in (e.get("location") or [])]


def fetch_events() -> List[Event]:
    try:
        raw = fetch_html(_BOOT_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    try:
        boot_json = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"[{_SOURCE}] failed to parse boot JSON")
        return []

    raw_events = _extract_events(boot_json)
    today = datetime.now(tz=_TZ).date()

    events: List[Event] = []
    for raw_event in raw_events:
        event = _parse_event(raw_event, today)
        if event:
            events.append(event)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
