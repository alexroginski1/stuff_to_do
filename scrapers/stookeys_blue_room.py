from __future__ import annotations

# Stookey's Blue Room's music/events page has no server-rendered event list —
# it's a Wix Events widget whose data ships inside a `#wix-warmup-data`
# script tag as SSR hydration state. The app/widget instance ids inside that
# state are opaque and can change across Wix deploys, so rather than hardcode
# a path into the JSON, this walks the whole tree looking for any dict shaped
# like the widget's events payload (`{"events": [...], "hasMore": ...}`).

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_CALENDAR_URL = "https://www.stookeysblueroom.com/musicandevents"
_ADDRESS = "891 Bush St, San Francisco, CA 94108"

_WARMUP_RE = re.compile(r'<script[^>]*id="wix-warmup-data"[^>]*>(.*?)</script>', re.S)


def _find_event_lists(node: Any) -> List[list]:
    found: List[list] = []
    if isinstance(node, dict):
        events = node.get("events")
        if isinstance(events, list) and "hasMore" in node:
            found.append(events)
        for value in node.values():
            found.extend(_find_event_lists(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_event_lists(item))
    return found


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_event(raw: dict, now: datetime) -> Optional[Event]:
    title = raw.get("title")
    slug = raw.get("slug")
    if not title or not slug:
        return None

    config = (raw.get("scheduling") or {}).get("config") or {}
    start = _parse_dt(config.get("startDate"))
    if not start:
        return None
    end = _parse_dt(config.get("endDate"))
    if (end or start) < now:
        return None

    return Event(
        name=title.strip(),
        start_time=start,
        end_time=end,
        location=_ADDRESS,
        description=(raw.get("description") or "").strip() or None,
        source_url=f"https://www.stookeysblueroom.com/event-details/{slug}",
        source=_SOURCE,
        location_verified=True,
    )


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_CALENDAR_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    m = _WARMUP_RE.search(html)
    if not m:
        logger.warning(f"[{_SOURCE}] warmup data script not found")
        return []

    try:
        warmup = json.loads(m.group(1))
    except json.JSONDecodeError:
        logger.warning(f"[{_SOURCE}] failed to parse warmup JSON")
        return []

    now = datetime.now(tz=timezone.utc)
    seen_ids: set[str] = set()
    events: List[Event] = []
    for event_list in _find_event_lists(warmup):
        for raw in event_list:
            event_id = raw.get("id")
            if event_id:
                if event_id in seen_ids:
                    continue
                seen_ids.add(event_id)
            event = _parse_event(raw, now)
            if event:
                events.append(event)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
