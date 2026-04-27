from __future__ import annotations

import json
import logging
import re
from typing import List

from bs4 import BeautifulSoup

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html, parse_iso_datetime

logger = logging.getLogger(__name__)

__SOURCE = Path(__file__).stem
URL = "https://www.thefaight.com/events"
LOCATION = "475 Haight St, San Francisco"


def _extract_initial_events(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    decoder = json.JSONDecoder()

    for script in soup.find_all("script"):
        text = (script.string or "").strip()
        if "initialEvents" not in text:
            continue

        for m in re.finditer(r'self\.__next_f\.push\(', text):
            try:
                arr, _ = decoder.raw_decode(text, m.end())
                if not (isinstance(arr, list) and len(arr) >= 2 and isinstance(arr[1], str)):
                    continue
                inner = arr[1]
                if "initialEvents" not in inner:
                    continue
                m2 = re.search(r'"initialEvents"\s*:\s*(\[)', inner)
                if not m2:
                    continue
                events_arr, _ = decoder.raw_decode(inner, m2.end() - 1)
                return events_arr
            except Exception:
                continue

    return []


def fetch_events() -> List[Event]:
    html = fetch_html(URL)
    raw_events = _extract_initial_events(html)

    events: List[Event] = []
    for raw in raw_events:
        if raw.get("isPrivate"):
            continue

        name = (raw.get("title") or "").strip()
        start_raw = raw.get("startTime")
        if not name or not start_raw:
            continue

        try:
            start_time = parse_iso_datetime(start_raw)
        except Exception:
            logger.warning(f"[{_SOURCE}] bad startTime {start_raw!r} for {name!r}")
            continue

        end_raw = raw.get("endTime")
        end_time = parse_iso_datetime(end_raw) if end_raw else None

        slug = (raw.get("slug") or {}).get("current", "")
        source_url = f"https://www.thefaight.com/events/{slug}" if slug else URL

        cta = raw.get("ctaUrl")
        if cta:
            source_url = cta

        events.append(Event(
            name=name,
            start_time=start_time,
            end_time=end_time,
            location=LOCATION,
            description=None,
            source_url=source_url,
            source=_SOURCE,
            unique_key=Event.build_unique_key(name, start_time),
        ))

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
