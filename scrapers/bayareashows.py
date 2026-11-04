from __future__ import annotations

import html
import json
import logging
import re
import string
from datetime import datetime, time
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_DISPLAY_URL = "https://bayareashows.org/"
# bayareashows.org is a React SPA backed by a public GCS bucket: sources.json
# lists every venue it scrapes, and each venue's events live at <name>.json.
_DATA_URL = "https://storage.googleapis.com/show-scraper-data/"
_TZ = ZoneInfo("America/Los_Angeles")

# Venues that already have their own dedicated scraper in this repo (feed
# name → display name) — skip them here so they don't show up twice.
_SKIP_VENUES = {
    "FourStarTheater": "4 Star Theater",
    "TheLab": "The Lab",
    "MakeOutRoom": "Make Out Room",
    "BoomBoomRoom": "Boom Boom Room",
    "GreyArea": "Gray Area",
}

# "The List" (foopee.com) aggregates shows across the whole Bay Area; each
# event's title is a JSON blob of {"venue": "CASTRO THEATER, S.F.", "artists": ...}.
_THE_LIST = "TheList"
_SF_SUFFIX = ", S.F."

# The feed's region labels aren't reliable (Elbo Room is tagged "San
# Francisco" but sits in Oakland), so also require the venue's coordinates
# to fall inside SF proper.
_SF_LAT = (37.70, 37.84)
_SF_LNG = (-122.53, -122.35)

# Many venues only publish a date. Those get pushed at a typical show start
# time, with a note in the description to check the venue for the real time.
_DEFAULT_START = time(20, 0)
_NO_TIME_NOTE = "Start time not listed — check the event link for the actual time."


def _fetch_json(name: str) -> list:
    return json.loads(fetch_html(f"{_DATA_URL}{name}.json"))


def _norm(name: str) -> str:
    name = re.sub(r"^the\s+", "", name.strip().lower())
    return re.sub(r"[^a-z0-9]", "", name)


def _in_sf(latlng: str) -> bool:
    try:
        lat, lng = (float(p) for p in latlng.split(","))
    except ValueError:
        return False
    return _SF_LAT[0] <= lat <= _SF_LAT[1] and _SF_LNG[0] <= lng <= _SF_LNG[1]


def _parse_start(raw: Optional[str]) -> tuple[Optional[datetime], bool]:
    """Return (local start, time_known) for one of the feed's ISO timestamps.

    The upstream per-venue scrapers are inconsistent about timezones:
    - "...-08:00"/"-07:00" are real offsets; midnight or noon there is a
      date-only placeholder.
    - "...+00:00" is sometimes true UTC (Fillmore's 04:00Z = 8pm PT) and
      sometimes local wall-clock time mislabeled as UTC (DNA Lounge's 21:30Z
      = 9:30pm). A real UTC show time lands roughly between 01:00Z and
      11:00Z, so anything from 12:00Z on is treated as local. 00:00Z is a
      date-only placeholder.
    """
    if not raw:
        return None, False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, False
    if dt.tzinfo is None or dt.utcoffset().total_seconds() == 0:
        wall = dt.replace(tzinfo=None)
        if wall.time() == time(0, 0):
            return wall.replace(tzinfo=_TZ), False
        if wall.hour >= 12:
            return wall.replace(tzinfo=_TZ), True
        local = dt.astimezone(_TZ)
    else:
        local = dt.astimezone(_TZ)
        if local.time().replace(microsecond=0) == time(12, 0):
            return local.replace(hour=0, minute=0, second=0, microsecond=0), False
    if local.time().replace(second=0, microsecond=0) == time(0, 0):
        return local.replace(hour=0, minute=0, second=0, microsecond=0), False
    return local.replace(second=0, microsecond=0), True


def _fix_mojibake(text: str) -> str:
    # The List occasionally comes through double-encoded ("Simonettiâ€™s").
    if "â€" not in text:
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text


def _description(details: str, time_known: bool) -> Optional[str]:
    parts = []
    if not time_known:
        parts.append(_NO_TIME_NOTE)
    if details:
        parts.append(details)
    return "\n\n".join(parts) or None


def _build_event(raw: dict, title: str, venue_name: str, location: str) -> Optional[Event]:
    title = _fix_mojibake(html.unescape((title or "").strip()))
    start, time_known = _parse_start(raw.get("date"))
    if not title or not start:
        return None
    if not time_known:
        start = start.replace(hour=_DEFAULT_START.hour, minute=_DEFAULT_START.minute)
    return Event(
        name=f"{title} @ {venue_name}",
        start_time=start,
        end_time=None,
        location=location,
        description=_description((raw.get("details") or "").strip(), time_known),
        source_url=raw.get("url") or _DISPLAY_URL,
        source=_SOURCE,
    )


def _matches(venue_key: str, keys) -> bool:
    return any(venue_key.startswith(k) or k.startswith(venue_key) for k in keys)


def _the_list_venue(raw_venue: str) -> Optional[tuple[str, str]]:
    """Map a The List venue like "TEQUILA MOCKINGBIRD, 86 2ND STREET, S.F." to
    (display name, geocodable location), or None if it isn't in SF."""
    raw_venue = raw_venue.strip()
    if not raw_venue.upper().endswith(_SF_SUFFIX):
        return None
    pieces = [p.strip() for p in raw_venue[: -len(_SF_SUFFIX)].split(",") if p.strip()]
    if not pieces:
        return None
    pieces = [string.capwords(p) for p in pieces]
    return pieces[0], ", ".join(pieces + ["San Francisco, CA"])


def fetch_events() -> List[Event]:
    today = datetime.now(tz=_TZ).date()
    venues = json.loads(fetch_html(f"{_DATA_URL}sources.json"))

    events: List[Event] = []
    skip_keys = {_norm(v) for v in _SKIP_VENUES.values()}
    # Normalized venue name → dates it already has events on from its own
    # feed, so The List's copy of the same show gets dropped.
    covered: dict[str, set] = {}

    for venue in venues:
        name = venue.get("name")
        if (
            not name
            or name in _SKIP_VENUES
            or venue.get("region") != "San Francisco"
            or not _in_sf(venue.get("latlng") or "")
        ):
            continue
        common_name = venue.get("commonName") or name
        try:
            raw_events = _fetch_json(name)
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch venue {name}: {exc}")
            continue
        dates = covered.setdefault(_norm(common_name), set())
        location = f"{common_name}, San Francisco, CA"
        for raw in raw_events:
            ev = _build_event(raw, raw.get("title"), common_name, location)
            if ev and ev.start_time.date() >= today:
                events.append(ev)
                dates.add(ev.start_time.date())

    try:
        the_list = _fetch_json(_THE_LIST)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch {_THE_LIST}: {exc}")
        the_list = []
    for raw in the_list:
        try:
            info = json.loads(raw.get("title") or "")
        except ValueError:
            continue
        mapped = _the_list_venue(info.get("venue") or "")
        if not mapped:
            continue
        venue_name, location = mapped
        ev = _build_event(raw, info.get("artists"), venue_name, location)
        if not ev or ev.start_time.date() < today:
            continue
        key = _norm(venue_name)
        same_day = [k for k, dates in covered.items() if ev.start_time.date() in dates]
        if _matches(key, skip_keys) or _matches(key, same_day):
            continue
        events.append(ev)

    logger.info(f"[{_SOURCE}] found {len(events)} events")
    return events
