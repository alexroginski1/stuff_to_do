from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_PAGE_URL = "https://setupcomedy.com/comedyshow-sanfrancisco"
_TZ = ZoneInfo("America/Los_Angeles")

# The shows page renders its list client-side from this published Google
# Sheet CSV (see the "EVENTS: fetch from Google Sheet CSV" block on the
# page), so we read it directly rather than scraping rendered HTML.
_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTGjBPXefy3N-RiCW15l_DaDovBB8d11X9PpGMRxUt_BRYzjoBtKUTyNhIf1AzaRJFLFxF71rMOWWku"
    "/pub?gid=495747966&single=true&output=csv"
)

# Every show runs at one of two known SF venues; addresses are hardcoded
# rather than left for Google Places to resolve from the bare venue name.
_VENUE_ADDRESSES = {
    "the palace theater": "644 Broadway, San Francisco, CA 94133",
    "the lost church": "988 Columbus Avenue, San Francisco, CA 94133",
}


def fetch_events() -> List[Event]:
    try:
        csv_text = fetch_html(_CSV_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events: List[Event] = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        date_str = (row.get("date") or "").strip()
        title = (row.get("title") or "").strip()
        if not date_str or not title:
            continue

        sold_out = (row.get("sold_out") or "").strip()
        urgency_tag = (row.get("urgency_tag") or "").strip()
        if sold_out or "sold out" in urgency_tag.lower():
            continue

        time_str = (row.get("time") or "").strip()
        try:
            if time_str:
                start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p").replace(tzinfo=_TZ)
            else:
                start_time = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_TZ)
        except ValueError:
            continue

        venue = (row.get("venue") or "").strip()
        location = _VENUE_ADDRESSES.get(venue.lower())

        ticket_url = (row.get("ticket_url") or "").strip() or _PAGE_URL

        events.append(
            Event(
                name=title,
                start_time=start_time,
                end_time=None,
                location=location,
                description=None,
                source_url=ticket_url,
                source=_SOURCE,
                location_verified=location is not None,
            )
        )

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
