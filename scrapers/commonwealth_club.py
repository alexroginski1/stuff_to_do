from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://www.commonwealthclub.org/events"
_MAX_PAGES = 20

_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _is_canceled(node) -> bool:
    link = node.select_one(".field--name-node-link a")
    if link is None:
        return False
    classes = link.get("class") or []
    return "inactive" in " ".join(classes) or link.get_text(strip=True).lower() == "canceled"


def _extract_address(soup: BeautifulSoup) -> Optional[str]:
    """Structured venue address on the event's detail page. Livestream-only
    events have no street/locality (just the org name), so those return None
    rather than a misleadingly geocodable string."""
    field = soup.select_one(".field--name-field-venue-address")
    if field is None:
        return None
    line1 = field.select_one(".address-line1")
    line2 = field.select_one(".address-line2")
    locality = field.select_one(".locality")
    region = field.select_one(".administrative-area")
    postal = field.select_one(".postal-code")
    if line2 is None or locality is None:
        return None
    parts = [
        line1.get_text(strip=True) if line1 else None,
        line2.get_text(strip=True),
        locality.get_text(strip=True),
        region.get_text(strip=True) if region else None,
        postal.get_text(strip=True) if postal else None,
    ]
    return ", ".join(p for p in parts if p) or None


def _fetch_detail(url: str) -> Optional[dict]:
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch detail {url}: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    location = _extract_address(soup)

    for raw in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in data.get("@graph", []):
            if item.get("@type") != "Event":
                continue
            start_raw = item.get("startDate")
            if not start_raw:
                continue
            # No offset/"Z" in the timestamp, but it's UTC (matches the PDT
            # time shown on the listing page once converted).
            start = datetime.fromisoformat(start_raw).replace(tzinfo=timezone.utc)
            end_raw = item.get("endDate")
            end = datetime.fromisoformat(end_raw).replace(tzinfo=timezone.utc) if end_raw else None
            return {
                "start": start,
                "end": end,
                "description": item.get("description"),
                "location": location,
            }

    return None


def _parse_listing(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for node in soup.select("div.node--type-event"):
        if _is_canceled(node):
            continue
        title_link = node.select_one(".field--name-node-title a")
        if title_link is None:
            continue
        name = title_link.get_text(strip=True)
        href = title_link.get("href")
        if not name or not href:
            continue
        rows.append({"name": name, "url": urljoin(_BASE_URL, href)})
    return rows


def fetch_events() -> List[Event]:
    rows: List[dict] = []
    for page in range(_MAX_PAGES):
        try:
            html = fetch_html(f"{_BASE_URL}?page={page}")
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break
        page_rows = _parse_listing(html)
        if not page_rows:
            break
        rows.extend(page_rows)

    events: List[Event] = []
    for row in rows:
        detail = _fetch_detail(row["url"])
        if not detail:
            continue
        events.append(
            Event(
                name=row["name"],
                start_time=detail["start"],
                end_time=detail["end"],
                location=detail["location"],
                description=detail["description"],
                source_url=row["url"],
                source=_SOURCE,
            )
        )

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
