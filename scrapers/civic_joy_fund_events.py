from __future__ import annotations

# Civic Joy Fund's own events page (https://civicjoyfund.org/events) is an
# Elfsight calendar widget backed by a public Google Calendar ("Civic Joy Fund
# Events"), read here through its public ICS export. That calendar mixes two
# kinds of events:
#
#   * neighborhood cleanups / park volunteering — the same events already
#     pulled from Mobilize by civic_joy_fund.py into SF Volunteering, but
#     re-entered by hand with different titles ("Clement St Cleanup" vs.
#     Mobilize's "Clement Street Happy Hour Cleanup") and slightly different
#     venue strings, so title-based dedup can't catch them;
#   * everything else — block parties, night markets, pop-up markets, etc. —
#     which only exists on this calendar.
#
# This source keeps only the second kind. To avoid duplicates, an event is
# dropped if either:
#   1. its title marks it as a cleanup / volunteering shift (those belong on
#      SF Volunteering via civic_joy_fund.py, not here); or
#   2. it lines up with an event another scraper already pushes — any Civic
#      Joy Fund Mobilize event (any tag, not just the Community Service tag
#      civic_joy_fund.py filters to), or a Sunset Mercantile event (it runs
#      Cole Valley / Sunset night markets, which also land on SF Community
#      but under different titles: "Cole Valley Nights" vs. this calendar's
#      "Cole Valley Night Market"). "Lines up" = start times within 30 min
#      and either the same street address or a clearly shared title.

import logging
import re
from datetime import timedelta
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.event_model import Event
from app.utils import fetch_mobilize_org_events
from scrapers import sunset_mercantile
from scrapers._google_calendar import fetch_google_calendar_events

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_CALENDAR_ID = "c_b0e78aa2d8125f99b281c06594c1e47e63f1bcb7c33e975f8b6d469204f6735f@group.calendar.google.com"
_DISPLAY_URL = "https://civicjoyfund.org/events"
_MOBILIZE_ORG_SLUG = "civicjoyfund"
_TZ = ZoneInfo("America/Los_Angeles")

_VOLUNTEER_TITLE_RE = re.compile(r"clean\s*-?\s*up|\bclean\b|volunteer|street\s+sweep", re.IGNORECASE)
# How far apart two listings' start times can be and still be the same event.
_TIME_TOLERANCE = timedelta(minutes=30)
# When addresses don't line up, titles count as the same event if they share
# at least _MIN_SHARED_WORDS distinctive words, or at least _TITLE_OVERLAP of
# them (Jaccard). One shared word alone isn't enough — "Ocean Avenue Block
# Party" vs. "KEEP Ocean Beach Clean" share "ocean" but are unrelated.
_MIN_SHARED_WORDS = 2
_TITLE_OVERLAP = 0.5
# Title words too generic to identify a specific event.
_GENERIC_WORDS = {
    "the", "a", "an", "and", "of", "at", "in", "on", "for", "to", "with", "sf", "san", "francisco",
    "st", "street", "ave", "avenue", "clean", "cleanup", "up", "weekly", "monthly", "community",
    "happy", "hour", "neighborhood", "keep", "civic", "joy", "corps", "fund", "day",
}


def _title_words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in _GENERIC_WORDS and len(w) > 2}


def _street_address(location: Optional[str]) -> Optional[str]:
    """'Ocean Beach Cafe, 734 La Playa St, San Francisco' -> '734 la'."""
    if not location:
        return None
    m = re.search(r"\b(\d+)\s+([A-Za-z]+)", location)
    return f"{m.group(1)} {m.group(2).lower()}" if m else None


def _matches(event: Event, other: Event) -> bool:
    if abs(event.start_time - other.start_time) > _TIME_TOLERANCE:
        return False
    address = _street_address(event.location)
    if address and address == _street_address(other.location):
        return True
    words, other_words = _title_words(event.name), _title_words(other.name)
    shared = words & other_words
    if not shared:
        return False
    return len(shared) >= _MIN_SHARED_WORDS or len(shared) / len(words | other_words) >= _TITLE_OVERLAP


def fetch_events() -> List[Event]:
    calendar_events = fetch_google_calendar_events(
        _CALENDAR_ID, _SOURCE, _TZ, _DISPLAY_URL, expand_recurring=True, keep_links=True
    )
    if not calendar_events:
        return []

    # No tag filter: some volunteering events on Mobilize aren't tagged
    # Community Service, and they still shouldn't be duplicated here.
    already_listed = fetch_mobilize_org_events(_MOBILIZE_ORG_SLUG, _SOURCE)
    try:
        already_listed += sunset_mercantile.fetch_events()
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] couldn't fetch Sunset Mercantile for dedup: {exc}")

    kept: List[Event] = []
    for event in calendar_events:
        if _VOLUNTEER_TITLE_RE.search(event.name):
            continue
        duplicate = next((other for other in already_listed if _matches(event, other)), None)
        if duplicate:
            logger.info(f"[{_SOURCE}] skipping {event.name!r}: already listed by {duplicate.source} as {duplicate.name!r}")
            continue
        kept.append(event)

    logger.info(f"[{_SOURCE}] kept {len(kept)} of {len(calendar_events)} calendar events")
    return kept
