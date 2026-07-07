from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.calendar_service import build_service, get_credentials
from app.event_model import Event

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_CALENDAR_ID = "6395b6c6ab85cf5ff3b6a1e59bc218ec592b74bfebf94821158bcf7e56c23ab1@group.calendar.google.com"


def _parse_dt(raw: dict) -> Optional[datetime]:
    if "dateTime" in raw:
        return datetime.fromisoformat(raw["dateTime"])
    if "date" in raw:
        return datetime.fromisoformat(raw["date"]).replace(tzinfo=timezone.utc)
    return None


def fetch_events() -> List[Event]:
    try:
        service = build_service(get_credentials())
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to build calendar service: {exc}")
        return []

    events: List[Event] = []
    page_token = None
    time_min = datetime.now(tz=timezone.utc).isoformat()

    try:
        while True:
            resp = service.events().list(
                calendarId=_CALENDAR_ID,
                singleEvents=True,
                orderBy="startTime",
                timeMin=time_min,
                maxResults=2500,
                pageToken=page_token,
            ).execute()

            for item in resp.get("items", []):
                name = item.get("summary")
                start = _parse_dt(item.get("start", {}))
                if not name or not start:
                    continue

                events.append(Event(
                    name=name,
                    start_time=start,
                    end_time=_parse_dt(item.get("end", {})),
                    location=item.get("location"),
                    description=item.get("description"),
                    source_url=item.get("htmlLink", ""),
                    source=_SOURCE,
                ))

            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] fetch failed: {exc}")
        return []

    logger.info(f"[{_SOURCE}] parsed {len(events)} events")
    return events
