from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://tickets.cttcomedy.com/events/"

# The events page renders server-side into a single JSON-LD @graph containing
# both "Event" and duplicate "ComedyClub" entries per show — only the "Event"
# entries carry start/end times, and each one already includes the venue's
# full address (all shows run at the same Shelton Theater location).
_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _format_address(location: dict) -> str | None:
    addr = location.get("address") or {}
    street = addr.get("streetAddress")
    city = addr.get("addressLocality")
    if not (street and city):
        return None
    parts = [location.get("name"), street, city, addr.get("addressRegion"), addr.get("postalCode")]
    return ", ".join(p for p in parts if p)


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events: List[Event] = []
    for raw in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for item in data.get("@graph", []):
            if item.get("@type") != "Event":
                continue

            name = item.get("name")
            start_raw = item.get("startDate")
            if not name or not start_raw:
                continue
            try:
                start_time = datetime.fromisoformat(start_raw)
            except ValueError:
                continue

            end_time = None
            end_raw = item.get("endDate")
            if end_raw:
                try:
                    end_time = datetime.fromisoformat(end_raw)
                except ValueError:
                    pass

            location = _format_address(item.get("location") or {})
            offers = item.get("offers") or [{}]
            source_url = offers[0].get("url") or (item.get("organizer") or {}).get("url") or _URL

            events.append(
                Event(
                    name=name,
                    start_time=start_time,
                    end_time=end_time,
                    location=location,
                    description=None,
                    source_url=source_url,
                    source=_SOURCE,
                    location_verified=location is not None,
                )
            )

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
