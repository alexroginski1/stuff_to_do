from __future__ import annotations

import html as html_lib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://www.sfmoma.org/events/"
_ADDRESS = "151 Third Street, San Francisco, CA 94103"
_TZ = ZoneInfo("America/Los_Angeles")

# The events page server-renders its listing into a JS assignment
# (`APP.data['archive_filter_posts'] = [...]`) rather than a plain API
# endpoint, so the page HTML itself is parsed as the data source.
_POSTS_MARKER = "APP.data['archive_filter_posts'] = "

# "supertitle" doubles as this feed's per-event category label (shown on
# each event card). Family-oriented programming is out of scope for this
# calendar, so it's dropped here.
_EXCLUDED_CATEGORIES = {"family studio", "family program"}


def _clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    plain = BeautifulSoup(html_lib.unescape(text), "html.parser").get_text(" ", strip=True)
    return plain or None


def _parse_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        combined = f"{date_str} {time_str or '00:00:00'}"
        return datetime.strptime(combined, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_TZ)
    except ValueError:
        return None


def _fetch_posts(html: str) -> List[dict]:
    idx = html.find(_POSTS_MARKER)
    if idx == -1:
        return []
    try:
        posts, _ = json.JSONDecoder().raw_decode(html, idx + len(_POSTS_MARKER))
    except json.JSONDecodeError:
        return []
    return posts


def _parse_event(post: dict) -> Optional[Event]:
    category = (post.get("supertitle") or "").strip().lower()
    if category in _EXCLUDED_CATEGORIES:
        return None

    name = _clean_text(post.get("post_title") or post.get("link_title"))
    url = post.get("permalink")
    if not name or not url:
        return None

    start = _parse_dt(post.get("StartDate"), post.get("StartTime"))
    if not start:
        return None

    # FinishTime is only meaningful when the event ends the same day it
    # starts; multi-day listings (e.g. member preview weekends) leave it
    # blank, so an end datetime isn't fabricated for those.
    end = None
    if post.get("FinishTime") and post.get("EndDate") == post.get("StartDate"):
        end = _parse_dt(post.get("EndDate"), post.get("FinishTime"))

    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=_ADDRESS,
        description=_clean_text(post.get("description")),
        source_url=url,
        source=_SOURCE,
        location_verified=True,
    )


def fetch_events() -> List[Event]:
    try:
        html = fetch_html(_URL)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch: {exc}")
        return []

    events = [event for post in _fetch_posts(html) if (event := _parse_event(post))]
    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
