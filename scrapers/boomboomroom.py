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
_BASE_URL = "https://boomboomroom.com/events/"
_ADDRESS = "1601 Fillmore St, San Francisco, CA 94115"
# Beyond the last real page, the site's WordPress pagination silently
# re-serves page 1's content instead of 404ing, so this loop stops itself by
# tracking which event URLs have already been seen rather than trusting a
# fixed page count.
_MAX_PAGES = 20

_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(\{.*?\})</script>', re.S)


def _parse_listing(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for link in soup.select("a#eventTitle.url[href]"):
        href = link.get("href")
        title_el = link.select_one("h2")
        name = title_el.get_text(strip=True) if title_el else link.get("title")
        if not href or not name:
            continue
        rows.append({"name": name, "url": urljoin(_BASE_URL, href)})
    return rows


def _fetch_detail(url: str) -> Optional[dict]:
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch detail {url}: {exc}")
        return None

    m = _LD_JSON_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    start_raw = data.get("startDate")
    if not start_raw:
        return None
    try:
        start = datetime.fromisoformat(start_raw)
    except ValueError:
        return None

    soup = BeautifulSoup(html, "html.parser")
    desc_el = soup.select_one(".singleEventDescription")
    description = None
    if desc_el and "emptyDesc" not in (desc_el.get("class") or []):
        description = desc_el.get_text("\n", strip=True) or None

    return {"start": start, "description": description}


def fetch_events() -> List[Event]:
    rows: List[dict] = []
    seen_urls: set[str] = set()

    for page in range(1, _MAX_PAGES + 1):
        page_url = _BASE_URL if page == 1 else urljoin(_BASE_URL, f"page/{page}/")
        try:
            html = fetch_html(page_url)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break

        page_rows = _parse_listing(html)
        new_rows = [r for r in page_rows if r["url"] not in seen_urls]
        if not new_rows:
            break

        rows.extend(new_rows)
        seen_urls.update(r["url"] for r in new_rows)

    events: List[Event] = []
    for row in rows:
        detail = _fetch_detail(row["url"])
        if not detail:
            continue
        events.append(
            Event(
                name=row["name"],
                start_time=detail["start"],
                end_time=None,
                location=_ADDRESS,
                description=detail["description"],
                source_url=row["url"],
                source=_SOURCE,
                location_verified=True,
            )
        )

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
