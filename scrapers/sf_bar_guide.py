from __future__ import annotations

# SF Bar Guide (https://www.sfbarguide.com/) lists recurring nightlife events
# (trivia, karaoke, comedy, etc.) at SF bars. It's a Next.js app that embeds
# its full data set as a React Server Components payload inline in the page
# HTML — a series of `self.__next_f.push([1, "<json-escaped string>"])` calls.
# One of those strings, once JSON-unescaped, contains a JS array whose last
# element is `{"initialBars": [...]}`: every bar, with its address and a list
# of recurring events (name, weekday/time, and a `verified_date` the site
# stamps on whenever a human last confirmed the listing is still accurate).
#
# There's no calendar of one-off dates here — each event is a recurring
# weekly/biweekly/monthly slot, so this scraper computes the next real-world
# occurrence itself rather than reading one off the page. The site also has
# no per-event category field, so the bar-event type prefix (Trivia, Karaoke,
# ...) is inferred from the event name via keyword matching, checked against
# the site's own /event-type/<slug> pages (~95% agreement on the events that
# appear there).

import json
import logging
import re
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://www.sfbarguide.com/"
_TZ = ZoneInfo("America/Los_Angeles")

# Only include events whose listing was verified within this many days.
_VERIFIED_WINDOW_DAYS = 21

_FOOTER_LINE = 'This event was parsed from <a href="https://www.sfbarguide.com/">the SF Bar Guide</a>'

_WEEKDAYS = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

# (emoji, label) per bar-event category; the emoji is prefixed onto the
# event title as "{emoji} {event name}" (the label itself is unused in the
# title but kept for logging/debugging).
_CATEGORY_META: dict[str, tuple[str, str]] = {
    "dance": ("🕺", "Dance"),
    "trivia": ("🧠", "Trivia"),
    "karaoke": ("🎤", "Karaoke"),
    "bingo": ("🔢", "Bingo"),
    "comedy": ("🎭", "Comedy"),
    "drag": ("👑", "Drag"),
    "open-mic": ("🎙️", "Open Mic"),
    "game-night": ("🎲", "Game Night"),
    "sports": ("🏈", "Sports"),
    "live-music": ("🎸", "Live Music"),
}
_DEFAULT_CATEGORY = ("🍻", "Bar Night")

# Checked in order — first keyword match wins. Ordered so more specific
# categories (e.g. "dance") are checked before broader ones ("live-music",
# which also matches "band"/"dj"/"music") that would otherwise shadow them.
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("dance", ["danc", "salsa", "latin night"]),
    ("trivia", ["trivia", "quiz"]),
    ("karaoke", ["karaoke"]),
    ("bingo", ["bingo"]),
    ("comedy", ["comedy", "stand-up", "standup", "improv", "roast", "late night laughs"]),
    ("drag", ["drag"]),
    ("open-mic", ["open mic", "open-mic"]),
    ("game-night", ["game night", "board game", "gameshow", "game show", "mahjong", "puzzle"]),
    ("sports", ["watch party", "sports", "bowling"]),
    ("live-music", ["live music", "live band", "jazz", "jam", "dj ", " dj", "band", "music", "guitar", "rock"]),
]


def _classify(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in lowered for kw in keywords):
            return _CATEGORY_META[category]
    return _DEFAULT_CATEGORY


def _extract_bars(html: str) -> list[dict]:
    """Find and parse the `initialBars` payload embedded in the page's RSC data.

    Each `self.__next_f.push([1, "..."])` call carries a JSON-escaped string;
    once unescaped, most are small React element trees, but one is a JS array
    ending in `{"initialBars": [...]}`. That's the one we want.
    """
    for raw in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S):
        try:
            decoded = json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            continue
        if '"initialBars"' not in decoded:
            continue
        start = decoded.find("[")
        if start == -1:
            continue
        try:
            parsed = json.loads(decoded[start:])
        except json.JSONDecodeError:
            continue
        for item in parsed:
            if isinstance(item, dict) and "initialBars" in item:
                return item["initialBars"]
    return []


def _parse_time(time_str: str) -> Optional[time]:
    try:
        return datetime.strptime(time_str.strip(), "%I:%M %p").time()
    except (ValueError, AttributeError):
        return None


def _next_weekday_on_or_after(start: date, weekday_idx: int) -> date:
    return start + timedelta(days=(weekday_idx - start.weekday()) % 7)


def _prev_weekday_on_or_before(start: date, weekday_idx: int) -> date:
    return start - timedelta(days=(start.weekday() - weekday_idx) % 7)


def _nth_weekday_of_month(year: int, month: int, weekday_idx: int, n: int) -> Optional[date]:
    first_of_month = date(year, month, 1)
    day = 1 + (weekday_idx - first_of_month.weekday()) % 7 + (n - 1) * 7
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _next_nth_weekday_occurrence(today: date, weekday_idx: int, n: int) -> Optional[date]:
    candidate = _nth_weekday_of_month(today.year, today.month, weekday_idx, n)
    if candidate is not None and candidate >= today:
        return candidate
    year, month = _next_month(today.year, today.month)
    return _nth_weekday_of_month(year, month, weekday_idx, n)


def _next_biweekly_occurrence(today: date, weekday_idx: int, anchor: date) -> date:
    """Best-effort: treats `anchor` (the listing's verified_date) as falling
    on an actual occurrence week, and picks whichever of the next two
    candidate weekdays is an even number of weeks from that anchor."""
    anchor_occurrence = _prev_weekday_on_or_before(anchor, weekday_idx)
    candidate = _next_weekday_on_or_after(today, weekday_idx)
    weeks_since_anchor = (candidate - anchor_occurrence).days // 7
    if weeks_since_anchor % 2 != 0:
        candidate += timedelta(days=7)
    return candidate


def _occurrence_date(event: dict, today: date) -> Optional[date]:
    recurrence_type = event.get("recurrence_type")

    if recurrence_type == "one_time":
        raw = event.get("specific_date")
        if not raw:
            return None
        try:
            specific_date = date.fromisoformat(raw)
        except ValueError:
            return None
        return specific_date if specific_date >= today else None

    weekday_idx = _WEEKDAYS.get(event.get("day_of_week"))
    if weekday_idx is None:
        return None

    skip_dates = set(event.get("skip_dates") or [])

    if recurrence_type == "weekly":
        candidate = _next_weekday_on_or_after(today, weekday_idx)
        for _ in range(6):
            if candidate.isoformat() not in skip_dates:
                return candidate
            candidate += timedelta(days=7)
        return None

    if recurrence_type == "biweekly":
        verified_raw = event.get("verified_date")
        if not verified_raw:
            return None
        try:
            anchor = date.fromisoformat(verified_raw)
        except ValueError:
            return None
        candidate = _next_biweekly_occurrence(today, weekday_idx, anchor)
        for _ in range(6):
            if candidate.isoformat() not in skip_dates:
                return candidate
            candidate += timedelta(days=14)
        return None

    if recurrence_type == "nth_weekday":
        week_of_month = event.get("week_of_month")
        if not week_of_month:
            return None
        return _next_nth_weekday_occurrence(today, weekday_idx, week_of_month)

    return None


def _is_recently_verified(event: dict, cutoff: date) -> Optional[date]:
    raw = event.get("verified_date")
    if not raw:
        return None
    try:
        verified_date = date.fromisoformat(raw)
    except ValueError:
        return None
    return verified_date if verified_date >= cutoff else None


def _parse_bar_events(bar: dict, today: date, cutoff: date) -> List[Event]:
    name = bar.get("name")
    address = bar.get("address")
    if not name or not address:
        return []
    location = address if "san francisco" in address.lower() else f"{address}, San Francisco, CA"
    source_url = bar.get("event_page_url") or bar.get("website") or _URL

    events: List[Event] = []
    for raw_event in bar.get("events", []):
        if _is_recently_verified(raw_event, cutoff) is None:
            continue

        event_name = raw_event.get("name")
        event_time = _parse_time(raw_event.get("time") or "")
        if not event_name or event_time is None:
            continue

        occurrence_date = _occurrence_date(raw_event, today)
        if occurrence_date is None:
            continue

        emoji, _label = _classify(f"{event_name} {raw_event.get('notes', '')}")
        description_parts = []
        notes = raw_event.get("notes")
        if notes:
            description_parts.append(notes)
        description_parts.append(_FOOTER_LINE)

        events.append(
            Event(
                name=f"{emoji} {event_name}",
                start_time=datetime.combine(occurrence_date, event_time, tzinfo=_TZ),
                end_time=None,
                location=location,
                description="\n\n".join(description_parts),
                source_url=source_url,
                source=_SOURCE,
            )
        )
    return events


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch {_URL}: {exc}")
        return []

    bars = _extract_bars(html)
    if not bars:
        logger.warning(f"[{_SOURCE}] no bars found in page payload")
        return []

    today = datetime.now(tz=_TZ).date()
    cutoff = today - timedelta(days=_VERIFIED_WINDOW_DAYS)

    events: List[Event] = []
    for bar in bars:
        events.extend(_parse_bar_events(bar, today, cutoff))

    logger.info(f"[{_SOURCE}] parsed {len(events)} events from {len(bars)} bars")
    return events
