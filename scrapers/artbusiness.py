from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
# Public iCal export of the "SF Art Galleries - Openings & Events" Google
# Calendar (embed: https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com).
_ICS_URL = "https://calendar.google.com/calendar/ical/33alanb%40gmail.com/public/basic.ics"
_DISPLAY_URL = "https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com&ctz=America%2FLos_Angeles"
_TZ = ZoneInfo("America/Los_Angeles")


def _unfold(text: str) -> List[str]:
    """Rejoin RFC 5545 continuation lines (lines starting with a space/tab) onto the property line they belong to."""
    lines = text.replace("\r\n", "\n").split("\n")
    unfolded: List[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_prop(line: str) -> Optional[tuple[str, str, str]]:
    if ":" not in line:
        return None
    key, value = line.split(":", 1)
    name, _, params = key.partition(";")
    return name, params, value


def _unescape(text: str) -> str:
    return (
        text.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_dt(value: str, params: str) -> Optional[datetime]:
    if "VALUE=DATE" in params:
        # All-day listing with no specific opening time; skip rather than guess.
        return None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(_TZ)
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=_TZ)
    except ValueError:
        return None


def _parse_event_block(lines: List[str]) -> Optional[Event]:
    props: dict[str, tuple[str, str]] = {}
    for line in lines:
        parsed = _parse_prop(line)
        if not parsed:
            continue
        name, params, value = parsed
        props.setdefault(name, (params, value))

    start_params, start_value = props.get("DTSTART", ("", ""))
    start = _parse_dt(start_value, start_params) if start_value else None
    if not start:
        return None

    name = _unescape(props.get("SUMMARY", ("", ""))[1]).strip()
    if not name:
        return None

    end = None
    if "DTEND" in props:
        end_params, end_value = props["DTEND"]
        end = _parse_dt(end_value, end_params)

    location = _unescape(props.get("LOCATION", ("", ""))[1]).strip() or None

    description = None
    description_raw = props.get("DESCRIPTION", ("", ""))[1]
    if description_raw:
        text = BeautifulSoup(_unescape(description_raw), "html.parser").get_text(separator=" ", strip=True)
        description = text or None

    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=location,
        description=description,
        source_url=_DISPLAY_URL,
        source=_SOURCE,
    )


def fetch_events() -> List[Event]:
    try:
        raw = fetch_html(_ICS_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch calendar: {exc}")
        return []

    now = datetime.now(tz=_TZ)
    events: List[Event] = []
    current_block: Optional[List[str]] = None

    for line in _unfold(raw):
        if line == "BEGIN:VEVENT":
            current_block = []
            continue
        if line == "END:VEVENT":
            if current_block is not None:
                event = _parse_event_block(current_block)
                if event and event.start_time >= now:
                    events.append(event)
            current_block = None
            continue
        if current_block is not None:
            current_block.append(line)

    logger.info(f"[{_SOURCE}] parsed {len(events)} events")
    return events
