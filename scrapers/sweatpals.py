from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from typing import Dict, Iterator, List, Optional
from zoneinfo import ZoneInfo

from app.event_model import Event
from app.utils import fetch_html, parse_iso_datetime

logger = logging.getLogger(__name__)

# Every SweatPals host page (sweatpals.com/host/<username>) lives in this one
# module, keyed by source name (config.settings.SOURCES key, with
# "module": "sweatpals"); app/sync_engine.py calls fetch_events(<source>).
_HOSTS: Dict[str, str] = {
    "excelsior_running_club": "excelsiorrunningclub",
    "running_wylder": "running_wylder",
    "that_girl_run_club": "thatgirlrunclub",
    "town_strides": "townstrides",
}

_HOST_URL = "https://www.sweatpals.com/host/{username}"
_EVENT_URL = "https://www.sweatpals.com/event/{alias}/{date}"
_TZ = ZoneInfo("America/Los_Angeles")
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|])")


def _host_series(next_data: dict, source: str) -> Iterator[dict]:
    """Every event series on a host page.

    The page is a Next.js app whose __NEXT_DATA__ embeds React Query's
    dehydrated cache. The host's listings sit under queries keyed
    ["events", <host user id>, <tab>] for each tab ("classes", "events",
    "retreats", "experiences"); the same series often appears under more
    than one tab, so callers dedupe.
    """
    queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    for query in queries:
        key = query.get("queryKey") or []
        if not key or key[0] != "events":
            continue
        for page in (query.get("state") or {}).get("data", {}).get("pages", []) or []:
            if page.get("hasMore"):
                logger.warning(f"[{source}] {key[-1]!r} tab has more events than the page embeds; only the first page is parsed")
            yield from page.get("data") or []


def _description(series: dict) -> Optional[str]:
    text = (series.get("description") or "").strip()
    if not text:
        return None
    # SweatPals descriptions are markdown: **bold**, plus backslash-escaped
    # literals (e.g. "\-" list dashes, "\*" asterisks). Swap escapes out for
    # placeholders so escaped asterisks don't get read as bold markers, then
    # restore them as plain characters.
    escapes: List[str] = []

    def _stash(m: re.Match) -> str:
        escapes.append(m.group(1))
        return f"\x00{len(escapes) - 1}\x00"

    text = _MD_ESCAPE_RE.sub(_stash, html.escape(text, quote=False))
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: escapes[int(m.group(1))], text)


def _occurrences(series: dict) -> Iterator[tuple[str, datetime, Optional[datetime]]]:
    """(local date, start, end) for each upcoming instance of a series.

    Recurring series carry `upcomingDays` — the real upcoming instances
    (already excluding skipped dates), each with UTC start `times` — so
    those are used as-is rather than re-expanding the series' `rrule`
    (which SweatPals stores in UTC, e.g. a Wednesday 6pm PT run is
    BYDAY=TH). One-off events fall back to their single instance.
    """
    duration = None
    if series.get("startDate") and series.get("endDate"):
        duration = parse_iso_datetime(series["endDate"]) - parse_iso_datetime(series["startDate"])

    days = series.get("upcomingDays") or []
    if days:
        for day in days:
            for t in day.get("times") or []:
                start = parse_iso_datetime(t).astimezone(_TZ)
                yield start.date().isoformat(), start, (start + duration) if duration else None
        return

    instance = series.get("instance") or series.get("startDate")
    if instance:
        start = parse_iso_datetime(instance).astimezone(_TZ)
        end_raw = series.get("instanceEndDate") or series.get("endDate")
        end = parse_iso_datetime(end_raw).astimezone(_TZ) if end_raw else None
        yield start.date().isoformat(), start, end


def fetch_sweatpals_host_events(username: str, source: str) -> List[Event]:
    try:
        match = _NEXT_DATA_RE.search(fetch_html(_HOST_URL.format(username=username)))
        if not match:
            raise RuntimeError("__NEXT_DATA__ not found on SweatPals host page")
        next_data = json.loads(match.group(1))
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch host page: {exc}")
        return []

    now = datetime.now(tz=_TZ)
    seen: set[tuple[str, str]] = set()
    events: List[Event] = []
    for series in _host_series(next_data, source):
        if series.get("publishingState") not in (None, "published"):
            continue
        name, alias = series.get("name"), series.get("alias")
        if not name:
            continue
        try:
            occurrences = list(_occurrences(series))
        except (ValueError, TypeError) as exc:
            logger.warning(f"[{source}] skipping series {series.get('id')!r} with bad dates: {exc}")
            continue
        for local_date, start, end in occurrences:
            dedup_key = (series.get("baseId") or series.get("id") or name, start.isoformat())
            if dedup_key in seen or (end or start) < now:
                continue
            seen.add(dedup_key)
            events.append(Event(
                name=name,
                start_time=start,
                end_time=end,
                location=series.get("addressName") or None,
                description=_description(series),
                source_url=_EVENT_URL.format(alias=alias, date=local_date) if alias else _HOST_URL.format(username=username),
                source=source,
            ))

    logger.info(f"[{source}] parsed {len(events)} events")
    return events


def fetch_events(source: str) -> List[Event]:
    if source not in _HOSTS:
        raise ValueError(f"Unknown SweatPals source {source!r} — add it to _HOSTS")
    return fetch_sweatpals_host_events(_HOSTS[source], source)
