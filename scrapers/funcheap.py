from __future__ import annotations

# SF Funcheap is a WordPress site.
# Events are listed at https://sf.funcheap.com/region/san-francisco/
# Each event: div.tanbox.post with span.title.entry-title > a for title/url
# Date/time: div.meta.archive-meta.date-time with data-event-date / data-event-date-end attrs
# Location (listing page): last bare <span> (no class) inside the meta div —
# this is only a neighborhood name (e.g. "Inner Sunset"), not a real address.
# Pagination: /page/N/ suffix; page 1 of ~25
#
# The listing page's location is too vague to geocode reliably, and doesn't
# carry a description, so each event's own page is fetched for a precise
# venue/address and the write-up text — see _fetch_detail.

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, NavigableString, Tag

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://sf.funcheap.com/region/san-francisco/"
_TZ = ZoneInfo("America/Los_Angeles")
_MAX_PAGES = 8
# Boilerplate disclaimer paragraph that Funcheap appends to every event page;
# it's identical everywhere and adds no per-event information.
_DISCLAIMER_PREFIX = "Disclaimer:"
# Wrapper elements on the event page that are ads/social widgets, not content.
_SKIP_CLASSES = ("addthis", "fb-like", "submitted-organizer", "media-credit-container")


def _page_url(page: int) -> str:
    if page == 1:
        return _BASE_URL
    return f"{_BASE_URL}page/{page}/"


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)
    except (ValueError, TypeError):
        return None


def _has_skip_class(tag: Tag) -> bool:
    classes = tag.get("class")
    if not classes:
        return False
    joined = " ".join(classes)
    return any(skip in joined for skip in _SKIP_CLASSES)


def _parse_detail_location(soup: BeautifulSoup) -> Optional[str]:
    """Venue name + address from an event's own page, e.g.
    "JFK Drive Lindy Hop Spot, JFK Dr. & Music Concourse Dr, San Francisco, CA".

    This lives in div#stats as `<a>Venue Name</a> | Address text` immediately
    before a `div.region-links` (a row of neighborhood/city tag links). Walk
    backwards from region-links, skipping the inline <style> block that
    precedes it, to pull the address text and then the venue-name anchor.
    """
    stats = soup.find("div", id="stats")
    if stats is None:
        return None
    region_links = stats.find("div", class_="region-links")
    if region_links is None:
        return None

    address: Optional[str] = None
    sib = region_links.previous_sibling
    while sib is not None:
        if isinstance(sib, NavigableString):
            text = str(sib).strip()
            if text:
                address = text.lstrip("|").strip()
                break
        elif isinstance(sib, Tag) and sib.name != "style":
            break
        sib = sib.previous_sibling

    venue_name: Optional[str] = None
    if sib is not None:
        sib = sib.previous_sibling
        while sib is not None:
            if isinstance(sib, Tag) and sib.name == "a":
                venue_name = sib.get_text(strip=True) or None
                break
            if isinstance(sib, NavigableString) and str(sib).strip():
                break
            sib = sib.previous_sibling

    return ", ".join(p for p in (venue_name, address) if p) or None


def _parse_detail_description(soup: BeautifulSoup) -> Optional[str]:
    """The event write-up text from an event's own page: the top-level <p>
    and <blockquote> blocks inside div.entry, with ad/social widgets and the
    boilerplate disclaimer paragraph stripped out."""
    post = soup.find("div", id=lambda i: i and i.startswith("post-"))
    entry = post.find("div", class_="entry") if post else None
    if entry is None:
        return None

    for tag in entry.find_all(["script", "style", "section", "iframe"]):
        tag.decompose()
    for tag in entry.find_all(_has_skip_class):
        tag.decompose()

    parts = []
    for block in entry.find_all(["p", "blockquote"]):
        if block.find_parent(["p", "blockquote"]) is not None:
            continue
        text = " ".join(block.get_text(" ", strip=True).split())
        if text and not text.startswith(_DISCLAIMER_PREFIX):
            parts.append(text)

    return "\n\n".join(parts) or None


def _fetch_detail(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch an event's own page and return (location, description). Best
    effort: falls back to (None, None) on any failure so callers can keep the
    listing-page location and simply omit the description."""
    try:
        soup = BeautifulSoup(fetch_html(url), "html.parser")
        return _parse_detail_location(soup), _parse_detail_description(soup)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch detail page {url}: {exc}")
        return None, None


def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for meta in soup.find_all("div", class_=lambda c: c and "archive-meta" in c):
        start_raw = meta.get("data-event-date")
        end_raw = meta.get("data-event-date-end")

        start = _parse_dt(start_raw)
        if start is None:
            continue
        end = _parse_dt(end_raw)
        if end is not None and end < start:
            end += timedelta(days=1)

        # Location is the last bare span (no class attribute) in the meta div,
        # e.g. "The Function" or "Davies Symphony Hall" — a venue name with no
        # city/state, so append it for reliable geocoding.
        location: Optional[str] = None
        for span in meta.find_all("span", recursive=False):
            if not span.get("class"):
                location = span.get_text(strip=True) or None
        if location and "san francisco" not in location.lower():
            location = f"{location}, San Francisco, CA"

        # Title and URL are in the sibling span.title.entry-title > a
        parent = meta.parent
        title_span = parent.find("span", class_=lambda c: c and "entry-title" in c) if parent else None
        if title_span is None:
            continue
        anchor = title_span.find("a")
        if anchor is None:
            continue
        name = anchor.get_text(strip=True)
        url = anchor.get("href", "")
        if not name or not url:
            continue

        detail_location, description = _fetch_detail(url)
        location = detail_location or location

        events.append(Event(
            name=name,
            start_time=start,
            end_time=end,
            location=location,
            description=description,
            source_url=url,
            source=_SOURCE,
        ))

    return events


def fetch_events() -> List[Event]:
    all_events: List[Event] = []
    for page in range(1, _MAX_PAGES + 1):
        url = _page_url(page)
        try:
            html = fetch_html(url)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch page {page}: {exc}")
            break
        page_events = _parse_page(html)
        if not page_events:
            logger.info(f"[{_SOURCE}] no events on page {page}, stopping")
            break
        all_events.extend(page_events)
        logger.info(f"[{_SOURCE}] page {page}: {len(page_events)} events")

    return all_events
