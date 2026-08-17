from __future__ import annotations

# The Presidio's event calendar (https://presidio.gov/explore/events) is a
# Next.js frontend backed by the WordPress "The Events Calendar" plugin at
# wp.presidio.gov. Two data sources are combined:
#
# 1. The Tribe Events REST API (wp.presidio.gov/wp-json/tribe/events/v1/events)
#    gives every upcoming occurrence (start/end time + URL) cheaply, but its
#    `description`/`cost`/`venue` fields are always empty on this site.
# 2. Each event's own presidio.gov page embeds a Next.js __NEXT_DATA__ JSON
#    blob with the real content: `pageData.tribe_events.event_price`,
#    `.subheading`, `pageData.vc_event_location`, and a `long_description`
#    block with the full write-up.
#
# Recurring events (e.g. daily "Park Ranger Campfire Talks") produce one API
# occurrence per date but share the same URL slug (only the trailing date
# segment differs), and the slug's base URL (no date suffix) serves the same
# content for all of them. So detail pages are fetched once per distinct
# slug and reused across all of that series' occurrences.

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_EVENTS_API = "https://wp.presidio.gov/wp-json/tribe/events/v1/events"
_EVENT_PAGE_BASE = "https://presidio.gov/explore/events/"
_TZ = ZoneInfo("America/Los_Angeles")
_WINDOW_DAYS = 90
_MAX_PAGES = 10

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)


def _html_to_text(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    return text or None


def _parse_local_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ)
    except (ValueError, TypeError):
        return None


def _fetch_occurrences() -> List[dict]:
    """List every upcoming event occurrence in the fetch window via the
    Tribe Events REST API. Unbounded (no end_date filter) this endpoint
    returns 1500+ occurrences stretching years into the future because of
    daily recurring events, so the window keeps this to what's actually
    useful to show on the calendar."""
    today = datetime.now(tz=_TZ).date()
    end = today + timedelta(days=_WINDOW_DAYS)

    occurrences: List[dict] = []
    page = 1
    while page <= _MAX_PAGES:
        try:
            resp = fetch_html(
                _EVENTS_API
                + f"?per_page=50&page={page}&start_date={today}&end_date={end}"
            )
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch events page {page}: {exc}")
            break

        data = json.loads(resp)
        events = data.get("events", [])
        if not events:
            break

        occurrences.extend(events)

        if page >= data.get("total_pages", page):
            break
        page += 1

    return occurrences


def _fetch_detail(slug: str) -> dict:
    """Fetch the shared per-series content (price, description, location)
    from the slug's base event page, e.g.
    https://presidio.gov/explore/events/park-ranger-campfire-talks-2/ —
    without a trailing date, this serves the same content for every
    occurrence of that event."""
    url = f"{_EVENT_PAGE_BASE}{slug}/"
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch detail page {url}: {exc}")
        return {}

    match = _NEXT_DATA_RE.search(html)
    if not match:
        return {}
    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}

    page_data = next_data.get("props", {}).get("pageProps", {}).get("pageData", {})
    tribe = page_data.get("tribe_events", {}) or {}

    # `block` is a dict keyed by index ("0", "1", ...) on event detail pages,
    # but a plain list on other page types — normalize to an iterable of blocks.
    blocks = page_data.get("block") or {}
    if isinstance(blocks, dict):
        blocks = blocks.values()

    long_desc = None
    for block in blocks:
        if block.get("acf_fc_layout") == "long_description":
            long_desc = (
                (block.get("data", {}) or {})
                .get("long_description", {})
                .get("long_desc")
            )
            break

    return {
        "location": (page_data.get("vc_event_location") or "").strip() or None,
        "subheading": _html_to_text(tribe.get("subheading")),
        "long_description": _html_to_text(long_desc),
        "price": _html_to_text(tribe.get("event_price")),
    }


def _build_description(detail: dict) -> Optional[str]:
    parts = []
    price = detail.get("price")
    if price:
        parts.append(f"Price: {price}")
    if detail.get("subheading"):
        parts.append(detail["subheading"])
    if detail.get("long_description"):
        parts.append(detail["long_description"])
    return "\n\n".join(parts) or None


def fetch_events() -> List[Event]:
    occurrences = _fetch_occurrences()

    details: dict[str, dict] = {}
    events: List[Event] = []

    for occ in occurrences:
        start = _parse_local_dt(occ.get("start_date", ""))
        end = _parse_local_dt(occ.get("end_date", ""))
        name = occ.get("title")
        url = occ.get("url")
        slug = occ.get("slug")
        if not (start and name and url and slug):
            continue

        if slug not in details:
            details[slug] = _fetch_detail(slug)
        detail = details[slug]

        events.append(
            Event(
                name=name,
                start_time=start,
                end_time=end,
                location=detail.get("location"),
                description=_build_description(detail),
                source_url=url,
                source=_SOURCE,
            )
        )

    logger.info(
        f"[{_SOURCE}] fetched {len(events)} occurrences across {len(details)} event series"
    )
    return events
