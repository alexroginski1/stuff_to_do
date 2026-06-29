from __future__ import annotations

import json
import logging
from typing import List

from bs4 import BeautifulSoup

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html, parse_iso_datetime
from config.settings import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URLS = [
    "https://partiful.com/explore/sf",
    "https://partiful.com/explore/sf?tag=music",
    "https://partiful.com/explore/sf?tag=community",
    "https://partiful.com/explore/sf?tag=arts",
]


def _extract_raw(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "description": raw.get("description"),
        "start": raw.get("startDate"),
        "end": raw.get("endDate"),
        "timezone": raw.get("timezone") or DEFAULT_TIMEZONE,
        "location": " ".join(
            raw.get("locationInfo", {}).get("displayAddressLines", [])
        ).strip() or None,
        "url": f"https://partiful.com/e/{raw.get('id')}",
    }


def _parse_page(next_data: dict) -> List[dict]:
    page = next_data["props"]["pageProps"]
    raws: List[dict] = []

    for item in page.get("trendingSection", {}).get("items", []):
        if item.get("type") == "event":
            raws.append(_extract_raw(item["event"]))

    for section in page.get("sections", []):
        for item in section.get("items", []):
            if item.get("type") == "event":
                raws.append(_extract_raw(item["event"]))

    return raws


def _to_event(raw: dict) -> Event:
    start = parse_iso_datetime(raw["start"])
    end = parse_iso_datetime(raw["end"]) if raw.get("end") else None
    name = raw["title"]
    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=raw.get("location"),
        description=raw.get("description"),
        source_url=raw["url"],
        source=_SOURCE,
        unique_key=Event.build_unique_key(name, start),
    )


def _fetch_raws(url: str) -> List[dict]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script:
        raise RuntimeError(f"__NEXT_DATA__ not found on Partiful page: {url}")
    return _parse_page(json.loads(script.string))


def fetch_events() -> List[Event]:
    events: List[Event] = []
    seen_ids: set[str] = set()

    for url in _URLS:
        try:
            raws = _fetch_raws(url)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch {url}: {exc}")
            continue

        for raw in raws:
            event_id = raw.get("id")
            if event_id in seen_ids:
                continue
            if event_id:
                seen_ids.add(event_id)
            if not raw.get("start"):
                logger.warning(f"Skipping event with no start date: {raw.get('id')}")
                continue
            try:
                events.append(_to_event(raw))
            except Exception as exc:
                logger.warning(f"Skipping malformed event {raw.get('id')!r}: {exc}")

    return events
