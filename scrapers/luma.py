from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from app.event_model import Event
from app.tracked_event_store import EventGone, collect_explore_events
from app.utils import fetch_html

logger = logging.getLogger(__name__)

# Every Luma-backed source lives in this one module. Each keeps its own
# source name (config.settings.SOURCES key, with "module": "luma") so its
# calendar events stay tagged the same; app/sync_engine.py calls
# fetch_events(<source name>).
_EXPLORE_SOURCE = "luma"
_EXPLORE_URL = "https://api2.luma.com/discover/get-paginated-events?discover_place_api_id=discplace-BDj7GNbGlsF7Cka&pagination_limit=50"
_EVENT_URL = "https://api2.luma.com/event/get?event_api_id={api_id}"


@dataclass(frozen=True)
class _Calendar:
    url: str
    # Drop events whose Luma geo city isn't San Francisco.
    sf_only: bool = False
    # Hardcoded, known-correct address for every event (skips Google Places).
    address: Optional[str] = None
    # Drop events whose title contains any of these (case-insensitive).
    exclude_title_substrings: tuple[str, ...] = ()


def _cal(calendar_api_id: str, **kwargs) -> _Calendar:
    return _Calendar(
        f"https://api.luma.com/calendar/get-items?calendar_api_id={calendar_api_id}&pagination_limit=20&period=future",
        **kwargs,
    )


def _user(user_api_id: str, **kwargs) -> _Calendar:
    return _Calendar(
        f"https://api.luma.com/user/profile/events-hosting?user_api_id={user_api_id}&period=future",
        **kwargs,
    )


# Specific Luma calendars / host profiles, keyed by source name.
_CALENDARS: Dict[str, _Calendar] = {
    "luma_future_of_us": _cal("cal-aUwxXUURWQ7Nz2A"),
    "luma_grayarea": _user("usr-PLOuy4AkSzqdEvc", sf_only=True),
    "luma_muddywaters": _cal("cal-PzSmtxk8gXjzzt7"),
    # The Commons doesn't reliably expose a usable address via Luma's geo
    # data (often obfuscated down to just "Hayes Valley"), so hardcode it.
    "luma_the_commons": _cal(
        "cal-ahTi4ptrN9WCYkg",
        address="550 Laguna St, San Francisco",
        exclude_title_substrings=("members only",),
    ),
    "luma_tiat": _cal("cal-twiOosdGMMY66DI"),
    "sf_climate_action_club": _cal("cal-RvOUbuCkgxzowHT", sf_only=True),
    "sf_craft_club": _user("usr-Bz2fgNXYkRygsqe", sf_only=True),
    "the_sf_contemplarium": _cal("cal-8yYt1wEolssZz57"),
    "unplug_and_play_collective": _cal("cal-uxBDdVsoR4vaIaB", sf_only=True),
}

_TZ = ZoneInfo("America/Los_Angeles")
# Luma's list endpoints are cursor-paginated (`has_more` + `next_cursor`,
# passed back as `pagination_cursor`) and sorted by start time. A single page
# only reaches ~1 week out on busy calendars, so keep following the cursor
# until a page reaches past the sync engine's 14-day lookahead
# (app/sync_engine.py _LOOKAHEAD_DAYS) plus a small buffer.
_HORIZON_DAYS = 16
_MAX_PAGES = 10


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ)
    except Exception:
        return None


def _render_marks(text: str, marks: List[dict], skip_bold: bool = False) -> str:
    text = html.escape(text)
    for mark in marks:
        mtype = mark.get("type")
        if mtype == "bold":
            if not skip_bold:
                text = f"<b>{text}</b>"
        elif mtype == "italic":
            text = f"<i>{text}</i>"
        elif mtype == "link":
            href = mark.get("attrs", {}).get("href")
            if href:
                text = f'<a href="{html.escape(href, quote=True)}">{text}</a>'
    return text


def _render_inline(nodes: list, skip_bold: bool = False) -> str:
    parts = []
    for node in nodes:
        ntype = node.get("type")
        if ntype == "text":
            parts.append(_render_marks(node.get("text", ""), node.get("marks", []), skip_bold=skip_bold))
        elif ntype == "hard_break":
            parts.append("\n")
        else:
            parts.append(_render_inline(node.get("content", []), skip_bold=skip_bold))
    return "".join(parts)


def _render_block(node: dict) -> str:
    """Render a single ProseMirror block node (and its children) to formatted text."""
    ntype = node.get("type")
    if ntype == "paragraph":
        return _render_inline(node.get("content", []))
    if ntype == "heading":
        # Heading text nodes are already marked bold by Luma; skip_bold avoids
        # double-wrapping since the whole heading gets one <b> below.
        return f"<b>{_render_inline(node.get('content', []), skip_bold=True)}</b>"
    if ntype == "horizontal_rule":
        return "――――――――――"
    if ntype == "list_item":
        return "\n".join(_render_block(child) for child in node.get("content", []))
    if ntype in ("bullet_list", "ordered_list"):
        lines = []
        for i, item in enumerate(node.get("content", []), start=1):
            prefix = f"{i}. " if ntype == "ordered_list" else "• "
            lines.append(prefix + _render_block(item))
        return "\n".join(lines)
    # Fallback for unrecognized block types: recurse into children.
    return _render_inline(node.get("content", [])) if node.get("content") else node.get("text", "")


def _render_doc(doc: dict) -> str:
    """Render a Luma description_mirror (ProseMirror-style) doc, preserving paragraphs,
    line breaks, lists, headings, and bold/italic/link formatting as inline HTML."""
    blocks = [_render_block(node) for node in doc.get("content", [])]
    lines = [line.rstrip() for line in "\n\n".join(b for b in blocks if b.strip()).split("\n")]
    return "\n".join(lines).strip()


def _fetch_detail(api_id: str) -> dict:
    """Luma's per-event endpoint: the same `event` object as list entries,
    plus the full `description_mirror`. Raises EventGone on a 404."""
    try:
        return json.loads(fetch_html(_EVENT_URL.format(api_id=api_id)))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise EventGone(api_id) from exc
        raise


def _fetch_description(api_id: str) -> str:
    try:
        doc = _fetch_detail(api_id).get("description_mirror")
        return _render_doc(doc) if doc else ""
    except Exception as exc:
        logger.warning(f"Failed to fetch description for {api_id}: {exc}")
        return ""


def _is_sf(ev: dict) -> bool:
    city = ((ev.get("geo_address_info") or {}).get("city") or "").lower()
    return "san francisco" in city


def _to_raw(ev: dict, description: str) -> Optional[dict]:
    """Normalize a Luma `event` object into a plain, Firestore-storable dict."""
    start = _parse_dt(ev.get("start_at"))
    if not ev.get("name") or not start:
        return None
    end = _parse_dt(ev.get("end_at"))
    geo = ev.get("geo_address_info") or {}
    url_slug = ev.get("url")
    return {
        "id": ev.get("api_id"),
        "title": ev["name"],
        "start": start.isoformat(),
        "end": end.isoformat() if end else None,
        # Luma gives a full geocodable address (`full_address`) for events
        # with `mode: "shown"`, but hides it behind just a neighborhood
        # (`sublocality`) for events with `mode: "obfuscated"` until you
        # RSVP. Use the precise address when available; fall back to the
        # neighborhood name alone, then city, rather than guessing.
        "location": geo.get("full_address") or geo.get("sublocality") or geo.get("city"),
        "description": description,
        "url": f"https://luma.com/{url_slug}" if url_slug else "",
    }


def _raw_to_event(raw: dict, source: str) -> Event:
    end = raw.get("end")
    return Event(
        name=raw["title"],
        start_time=datetime.fromisoformat(raw["start"]).astimezone(_TZ),
        end_time=datetime.fromisoformat(end).astimezone(_TZ) if end else None,
        location=raw.get("location"),
        description=raw.get("description") or "",
        source_url=raw.get("url") or "",
        source=source,
    )


def _parse_entries(entries: List[dict], sf_only: bool = False) -> List[dict]:
    """Raw dicts for every list entry starting within the horizon, each with
    its full description fetched."""
    raws: List[dict] = []
    horizon = datetime.now(tz=_TZ) + timedelta(days=_HORIZON_DAYS)
    for entry in entries:
        ev = entry.get("event") or {}
        if sf_only and not _is_sf(ev):
            continue
        start = _parse_dt(ev.get("start_at"))
        # Past the lookahead — skip before spending a description API call.
        if not start or start > horizon:
            continue
        description = _fetch_description(ev["api_id"]) if ev.get("api_id") else ""
        raw = _to_raw(ev, description)
        if raw:
            raws.append(raw)
    return raws


def _fetch_entries(url: str, source: str) -> List[dict]:
    """Follow Luma's cursor pagination until the results pass the horizon."""
    horizon = datetime.now(tz=_TZ) + timedelta(days=_HORIZON_DAYS)
    entries: List[dict] = []
    cursor: Optional[str] = None
    for page in range(1, _MAX_PAGES + 1):
        page_url = f"{url}&pagination_cursor={quote(cursor)}" if cursor else url
        try:
            data = json.loads(fetch_html(page_url))
        except Exception as exc:
            logger.warning(f"[{source}] fetch failed on page {page}: {exc}")
            break
        page_entries = data.get("entries", [])
        entries.extend(page_entries)

        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor or not page_entries:
            break
        last_start = _parse_dt((page_entries[-1].get("event") or {}).get("start_at"))
        if last_start and last_start > horizon:
            break
    return entries


def _to_events(raws: List[dict], source: str) -> List[Event]:
    events: List[Event] = []
    for raw in raws:
        try:
            events.append(_raw_to_event(raw, source))
        except Exception as exc:
            logger.warning(f"[{source}] skipping malformed event {raw.get('id')!r}: {exc}")
    return events


def _recheck_event(api_id: str) -> dict:
    """Refetch a tracked explore event; EventGone if Luma no longer has it."""
    data = _fetch_detail(api_id)
    ev = data.get("event") or {}
    doc = data.get("description_mirror")
    raw = _to_raw(ev, _render_doc(doc) if doc else "")
    if raw is None:
        raise EventGone(api_id)
    return raw


def _fetch_explore_events() -> List[Event]:
    """luma.com/sf discover feed, accumulated across runs.

    The discover feed is a curated, changing subset, so every SF event seen
    there is remembered (app/tracked_event_store.py) and kept on the
    calendar until it ends, rather than vanishing as soon as Luma stops
    featuring it. Tracked events no longer featured are re-checked against
    Luma's event API each run, and dropped once it 404s.
    """
    entries = _fetch_entries(_EXPLORE_URL, _EXPLORE_SOURCE)
    featured = {raw["id"]: raw for raw in _parse_entries(entries, sf_only=True) if raw.get("id")}
    raws = collect_explore_events(_EXPLORE_SOURCE, featured, _recheck_event, _HORIZON_DAYS)
    return _to_events(raws, _EXPLORE_SOURCE)


def _fetch_calendar_events(source: str, cal: _Calendar) -> List[Event]:
    entries = _fetch_entries(cal.url, source)
    events = _to_events(_parse_entries(entries, sf_only=cal.sf_only), source)
    if cal.exclude_title_substrings:
        events = [
            e for e in events
            if not any(s in e.name.lower() for s in cal.exclude_title_substrings)
        ]
    if cal.address:
        for event in events:
            event.location = cal.address
            event.location_verified = True
    logger.info(f"[{source}] parsed {len(events)} events")
    return events


def fetch_events(source: str = _EXPLORE_SOURCE) -> List[Event]:
    if source == _EXPLORE_SOURCE:
        return _fetch_explore_events()
    if source not in _CALENDARS:
        raise ValueError(f"Unknown Luma source {source!r} — add it to _CALENDARS")
    return _fetch_calendar_events(source, _CALENDARS[source])
