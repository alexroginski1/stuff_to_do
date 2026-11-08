from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from app.event_model import Event
from app.utils import fetch_html, parse_iso_datetime

logger = logging.getLogger(__name__)

_GROUP_EVENTS_URL = "https://www.meetup.com/{group_urlname}/events/"
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _extract_apollo_state(html_text: str) -> dict:
    match = _NEXT_DATA_RE.search(html_text)
    if not match:
        raise RuntimeError("__NEXT_DATA__ not found on Meetup page")
    next_data = json.loads(match.group(1))
    return next_data["props"]["pageProps"]["__APOLLO_STATE__"]


def _is_placeholder(value: Optional[str]) -> bool:
    """Venue text hosts use when the real spot isn't announced yet, e.g.
    "TBD" or "Somewhere in San Francisco"."""
    v = (value or "").strip().lower()
    return v in {"tbd", "tba", "tbc"} or v.startswith("somewhere")


def _location(apollo: dict, event_raw: dict) -> Optional[str]:
    venue_ref = (event_raw.get("venue") or {}).get("__ref")
    if not venue_ref:
        return None
    venue = apollo.get(venue_ref) or {}
    place = venue.get("address") or venue.get("name")
    if _is_placeholder(place) or _is_placeholder(venue.get("name")):
        return None
    parts = [place, venue.get("city"), venue.get("state")]
    return ", ".join(p for p in parts if p) or None


def _to_event(apollo: dict, event_raw: dict, source: str, title_prefix: str) -> Optional[Event]:
    title = event_raw.get("title")
    start = event_raw.get("dateTime")
    if not title or not start:
        return None

    end = event_raw.get("endTime")
    return Event(
        name=f"{title_prefix}{title}",
        start_time=parse_iso_datetime(start),
        end_time=parse_iso_datetime(end) if end else None,
        location=_location(apollo, event_raw),
        description=event_raw.get("description"),
        source_url=event_raw.get("eventUrl"),
        source=source,
    )


def fetch_meetup_group_events(group_urlname: str, source: str, title_prefix: str = "") -> List[Event]:
    """Fetch upcoming events for a Meetup group (meetup.com/<group_urlname>).

    Meetup's group events page is a Next.js app whose __NEXT_DATA__ payload
    embeds a flat Apollo GraphQL cache (keyed "TypeName:id") with every
    entity referenced on the page, so every Event object present — including
    ones nested only as __ref pointers in the group's events connection —
    can be recovered directly by scanning the cache for __typename == "Event",
    without needing to know the group's internal GraphQL id or walk edges.
    """
    try:
        html_text = fetch_html(_GROUP_EVENTS_URL.format(group_urlname=group_urlname))
        apollo = _extract_apollo_state(html_text)
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch group page: {exc}")
        return []

    events: List[Event] = []
    for value in apollo.values():
        if not isinstance(value, dict) or value.get("__typename") != "Event":
            continue
        if value.get("status") != "ACTIVE":
            continue
        try:
            event = _to_event(apollo, value, source, title_prefix)
        except Exception as exc:
            logger.warning(f"[{source}] skipping malformed event {value.get('id')!r}: {exc}")
            continue
        if event:
            events.append(event)

    logger.info(f"[{source}] parsed {len(events)} events")
    return events
