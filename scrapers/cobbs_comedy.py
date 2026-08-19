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
_URL = "https://www.cobbscomedy.com/shows"
_ADDRESS = "915 Columbus Avenue, San Francisco, CA 94133, US"

# The shows page renders event data server-side into per-show JSON-LD blocks
# rather than exposing a stable per-event page we can link to, so every event
# just links back to the shows page itself.
_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    seen = set()
    events: List[Event] = []
    for raw in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "MusicEvent":
            continue

        name = data.get("name")
        start_raw = data.get("startDate")
        if not name or not start_raw:
            continue
        try:
            start_time = datetime.fromisoformat(start_raw)
        except ValueError:
            continue

        key = (name, start_time)
        if key in seen:
            continue
        seen.add(key)

        events.append(
            Event(
                name=name,
                start_time=start_time,
                end_time=None,
                location=_ADDRESS,
                description=None,
                source_url=_URL,
                source=_SOURCE,
                location_verified=True,
            )
        )

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
