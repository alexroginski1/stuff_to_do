from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
# The site renders its calendar client-side from this data file rather than
# server-rendered HTML; it's a hand-maintained near-JSON literal (unquoted
# keys, no trailing commas issues) rather than a real API response.
_EVENTS_JS_URL = "https://nights.themellowsf.com/js/events.js"
_CALENDAR_URL = "https://nights.themellowsf.com/#calendar"
_ADDRESS = "1401 Haight St, San Francisco, CA 94117"
_TZ = ZoneInfo("America/Los_Angeles")

_LEADERS_BLOCK_RE = re.compile(r"const LEADERS\s*=\s*\{(.*?)\n\};", re.S)
_LEADER_ENTRY_RE = re.compile(r"(\w+):\s*\{([^}]*)\}")
_SHOWS_BLOCK_RE = re.compile(r"const SHOWS\s*=\s*\{(.*?)\n\};", re.S)
_SHOW_ENTRY_RE = re.compile(r'"(\d{4}-\d{2}-\d{2})":\s*\{([^}]*)\}')
_LINEUP_RE = re.compile(r"lineup:\s*\[([^\]]*)\]")
_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_TRIO_RE = re.compile(r"\bTrio\b")


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _field(body: str, name: str) -> Optional[str]:
    m = re.search(name + r':\s*"((?:[^"\\]|\\.)*)"', body)
    return _unescape(m.group(1)) if m else None


def _parse_leaders(js: str) -> dict:
    block = _LEADERS_BLOCK_RE.search(js)
    if not block:
        return {}
    leaders = {}
    for key, body in _LEADER_ENTRY_RE.findall(block.group(1)):
        leaders[key] = {
            "display": _field(body, "display"),
            "name": _field(body, "name"),
            "bio": _field(body, "bio"),
        }
    return leaders


def _parse_lineup(body: str) -> List[str]:
    m = _LINEUP_RE.search(body)
    if not m:
        return []
    return [_unescape(item) for item in _STRING_RE.findall(m.group(1))]


def _event_name(leader: Optional[dict], lineup: List[str]) -> Optional[str]:
    billed = lineup[0] if lineup else ""
    name = (leader.get("display") or leader.get("name")) if leader else billed
    if not name:
        return None
    if _TRIO_RE.search(billed):
        name += " Trio"
    return name


def _parse_shows(js: str, leaders: dict) -> List[Event]:
    block = _SHOWS_BLOCK_RE.search(js)
    if not block:
        return []

    events: List[Event] = []
    for iso, body in _SHOW_ENTRY_RE.findall(block.group(1)):
        if "tba" in body:
            continue

        leader_key = _field(body, "leader")
        leader = leaders.get(leader_key) if leader_key else None
        lineup = _parse_lineup(body)

        name = _event_name(leader, lineup)
        if not name:
            continue

        try:
            night = datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            continue
        start_time = night.replace(hour=19, minute=0, tzinfo=_TZ)

        # Site charges $10 weekend cover (Fri/Sat), $5 otherwise.
        cover = 10 if start_time.weekday() in (4, 5) else 5

        description_parts = []
        if leader and leader.get("bio"):
            description_parts.append(leader["bio"])
        description_parts.append(
            f"Doors 7 PM • Sets 8:00 and ~9:20 • Cover ${cover}\nAll ages, 21+ to drink"
        )

        events.append(
            Event(
                name=name,
                start_time=start_time,
                end_time=None,
                location=_ADDRESS,
                description="\n\n".join(description_parts),
                source_url=_CALENDAR_URL,
                source=_SOURCE,
                location_verified=True,
            )
        )

    return events


def fetch_events() -> List[Event]:
    try:
        js = fetch_html(_EVENTS_JS_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    leaders = _parse_leaders(js)
    events = _parse_shows(js, leaders)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
