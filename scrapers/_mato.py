from __future__ import annotations

# Mato (ma.to) venue pages are a Next.js app with no separate JSON API
# endpoint for a venue's events -- the data is embedded directly in the
# initial page HTML as a React Server Component payload: a
# `self.__next_f.push([1, "..."])` call whose string argument is a
# JSON-escaped blob containing `"initialUpcoming":{"venue":{...},"events":[...]}`.
#
# So this fetches the venue page, finds the push() call that contains
# "initialUpcoming", unescapes its string argument back into normal JSON
# text, and then JSON-decodes just the `events` array out of that text
# (starting the decode at the array's opening bracket, since the
# surrounding text isn't valid JSON on its own).

import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

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


def _parse_event(raw: dict, source: str, address: str) -> Optional[Event]:
    name = raw.get("title")
    start = _parse_dt(raw.get("startDate"))
    if not name or not start:
        return None

    return Event(
        name=name.strip(),
        start_time=start,
        end_time=_parse_dt(raw.get("endDate")),
        location=address,
        description=raw.get("longDescription") or raw.get("description"),
        source_url=f"https://ma.to/event/{raw['slug']}" if raw.get("slug") else f"https://ma.to/venue/{source}",
        source=source,
        location_verified=True,
    )


def fetch_mato_venue_events(handle: str, source: str, address: str) -> List[Event]:
    """Fetch upcoming events off a Mato (ma.to) venue page.

    `handle` is the venue's slug in the ma.to URL
    (https://ma.to/venue/<handle>); `address` is hardcoded per venue since
    ma.to's own venue-level address field is often blank or inconsistent
    across a venue's events.
    """
    url = f"https://ma.to/venue/{handle}"
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch: {exc}")
        return []

    events: List[Event] = []
    for raw in _extract_events(html):
        event = _parse_event(raw, source, address)
        if event:
            events.append(event)

    logger.info(f"[{source}] found {len(events)} events")
    return events
