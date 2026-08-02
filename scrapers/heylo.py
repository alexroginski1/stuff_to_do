from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_GROUP_URL = "https://www.heylo.com/g/{group_id}"
_EVENT_URL = "https://www.heylo.com/event/{event_id}"
_TZ = ZoneInfo("America/Los_Angeles")

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _extract_next_data(html_text: str) -> dict:
    match = _NEXT_DATA_RE.search(html_text)
    if not match:
        raise RuntimeError("__NEXT_DATA__ not found on Heylo page")
    return json.loads(match.group(1))


def _find_query_data(next_data: dict, query_name: str) -> Optional[dict]:
    queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    for query in queries:
        if (query.get("queryKey") or [None])[0] == query_name:
            return query["state"]["data"]
    return None


def _parse_ms(ms: Optional[int]) -> Optional[datetime]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=_TZ)


def _fetch_event_previews(group_id: str) -> List[dict]:
    next_data = _extract_next_data(fetch_html(_GROUP_URL.format(group_id=group_id)))
    data = _find_query_data(next_data, "groupPage")
    return (data or {}).get("events", [])


def _fetch_event_detail(event_id: str, source: str) -> Optional[dict]:
    try:
        next_data = _extract_next_data(fetch_html(_EVENT_URL.format(event_id=event_id)))
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch event {event_id}: {exc}")
        return None
    data = _find_query_data(next_data, "event")
    return (data or {}).get("event")


def _to_event(detail: dict, source: str, title_prefix: str) -> Optional[Event]:
    name = detail.get("name")
    start = _parse_ms(detail.get("timestamp"))
    if not name or not start:
        return None

    location = detail.get("location") or (detail.get("locationData") or {}).get("label")
    event_id = detail["eventId"]

    return Event(
        name=f"{title_prefix}{name}",
        start_time=start,
        end_time=_parse_ms(detail.get("timestampEnd")),
        location=location,
        description=detail.get("notes"),
        source_url=_EVENT_URL.format(event_id=event_id),
        source=source,
    )


def fetch_heylo_events(group_id: str, source: str, title_prefix: str = "") -> List[Event]:
    try:
        previews = _fetch_event_previews(group_id)
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch group page: {exc}")
        return []

    events: List[Event] = []
    for preview in previews:
        event_id = preview.get("id")
        if not event_id:
            continue
        detail = _fetch_event_detail(event_id, source)
        if not detail:
            continue
        try:
            event = _to_event(detail, source, title_prefix)
        except Exception as exc:
            logger.warning(f"[{source}] skipping malformed event {event_id!r}: {exc}")
            continue
        if event:
            events.append(event)

    logger.info(f"[{source}] parsed {len(events)} events")
    return events
