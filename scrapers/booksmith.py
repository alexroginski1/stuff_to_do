from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_LISTING_URL = "https://booksmith.com/events/list/upcoming-events"
_DEFAULT_ADDRESS = "The Booksmith, 1727 Haight St, San Francisco, CA 94117"
# The site's bot filter 403s the shared session's full Chrome UA string but
# allows a bare one, so override it just for this scraper.
_HEADERS = {"User-Agent": "Mozilla/5.0"}

_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(\{.*?\})</script>', re.S)


def _parse_listing(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for article in soup.select("article.event-list"):
        link = article.select_one("h3.event-list__title a")
        if not link or not link.get("href"):
            continue
        name = link.get_text(strip=True)
        url = urljoin(_LISTING_URL, link["href"])
        rows.append({"name": name, "url": url})
    return rows


def _ld_json_event(html: str) -> Optional[dict]:
    """The page's JSON-LD @graph mixes an Event node in with a WebSite node;
    its location.address fields are buggy (fields concatenated together), so
    only startDate/endDate are trusted from here — location comes from the
    HTML address block instead."""
    m = _LD_JSON_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    for node in data.get("@graph", []):
        if node.get("@type") == "Event":
            return node
    return None


def _parse_location(soup: BeautifulSoup) -> str:
    # The address markup varies: most events use an <address> tag, but some
    # (e.g. off-site venues) use a Drupal <p class="address"> instead.
    container = soup.select_one(".event-details__location--location")
    address = container.select_one("address, p.address") if container else None
    if not address:
        return _DEFAULT_ADDRESS
    text = address.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text) or _DEFAULT_ADDRESS


def _fetch_detail(row: dict) -> Optional[Event]:
    try:
        html = fetch_html(row["url"], headers=_HEADERS)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch detail {row['url']}: {exc}")
        return None

    event_node = _ld_json_event(html)
    start_raw = event_node.get("startDate") if event_node else None
    if not start_raw:
        return None
    try:
        start_time = datetime.fromisoformat(start_raw)
    except ValueError:
        return None

    end_time = None
    end_raw = event_node.get("endDate") if event_node else None
    if end_raw:
        try:
            end_time = datetime.fromisoformat(end_raw)
        except ValueError:
            end_time = None

    soup = BeautifulSoup(html, "html.parser")
    desc_el = soup.select_one(".event-details__info--body")
    description = desc_el.get_text("\n", strip=True) if desc_el else None

    return Event(
        name=row["name"],
        start_time=start_time,
        end_time=end_time,
        location=_parse_location(soup),
        description=description or None,
        source_url=row["url"],
        source=_SOURCE,
        location_verified=True,
    )


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_LISTING_URL, headers=_HEADERS)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    rows = _parse_listing(html)

    events: List[Event] = []
    for row in rows:
        event = _fetch_detail(row)
        if event:
            events.append(event)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
