from __future__ import annotations

# The Saloon's own listing is on Mato (ma.to), a Next.js app that has no
# separate JSON API endpoint for a venue's events -- the data is embedded
# directly in the initial page HTML as a React Server Component payload:
# a `self.__next_f.push([1, "..."])` call whose string argument is a
# JSON-escaped blob containing `"initialUpcoming":{"venue":{...},"events":[...]}`.
#
# So this scraper fetches the venue page, finds the push() call that contains
# "initialUpcoming", unescapes its string argument back into normal JSON text,
# and then JSON-decodes just the `events` array out of that text (starting the
# decode at the array's opening bracket, since the surrounding text isn't
# valid JSON on its own).

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://ma.to/venue/thesaloonsf"
_ADDRESS = "1232 Grant Avenue, San Francisco, CA 94133"

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL)


def _extract_events(html: str) -> List[dict]:
    payload = None
    for m in _PUSH_RE.finditer(html):
        if "initialUpcoming" in m.group(1):
            payload = m.group(1)
            break
    if payload is None:
        return []

    try:
        decoded = json.loads('"' + payload + '"')
    except json.JSONDecodeError:
        return []

    idx = decoded.find('"events":[')
    if idx == -1:
        return []
    start = idx + len('"events":')

    try:
        events, _ = json.JSONDecoder().raw_decode(decoded, start)
    except json.JSONDecodeError:
        return []
    return events


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _parse_event(raw: dict) -> Optional[Event]:
    name = raw.get("title")
    start = _parse_dt(raw.get("startDate"))
    if not name or not start:
        return None

    return Event(
        name=name.strip(),
        start_time=start,
        end_time=_parse_dt(raw.get("endDate")),
        location=_ADDRESS,
        description=raw.get("longDescription") or raw.get("description"),
        source_url=f"https://ma.to/event/{raw['slug']}" if raw.get("slug") else _URL,
        source=_SOURCE,
        location_verified=True,
    )


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events: List[Event] = []
    for raw in _extract_events(html):
        event = _parse_event(raw)
        if event:
            events.append(event)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
