from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import parse_qs, quote, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil.rrule import rrulestr

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_ICS_URL_TEMPLATE = "https://calendar.google.com/calendar/ical/{calendar_id}/public/basic.ics"


def _unfold(text: str) -> List[str]:
    """Rejoin RFC 5545 continuation lines (lines starting with a space/tab) onto the property line they belong to."""
    lines = text.replace("\r\n", "\n").split("\n")
    unfolded: List[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_prop(line: str) -> Optional[tuple[str, str, str]]:
    if ":" not in line:
        return None
    key, value = line.split(":", 1)
    name, _, params = key.partition(";")
    return name, params, value


def _unescape(text: str) -> str:
    return (
        text.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_dt(value: str, params: str, tz: ZoneInfo) -> Optional[datetime]:
    if "VALUE=DATE" in params:
        # All-day listing with no specific time; skip rather than guess.
        return None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(tz)
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tz)
    except ValueError:
        return None


def _block_props(lines: List[str]) -> dict[str, tuple[str, str]]:
    props: dict[str, tuple[str, str]] = {}
    for line in lines:
        parsed = _parse_prop(line)
        if not parsed:
            continue
        name, params, value = parsed
        props.setdefault(name, (params, value))
    return props


def _unwrap_google_redirect(url: str) -> str:
    """Google Calendar rewrites some links as https://www.google.com/url?q=<real url>&sa=..."""
    parts = urlsplit(url)
    if parts.netloc.endswith("google.com") and parts.path == "/url":
        target = parse_qs(parts.query).get("q")
        if target:
            return target[0]
    return url


def _description_with_links(html_text: str) -> tuple[Optional[str], Optional[str]]:
    """Description text with each <a> kept as an inline link (like the Luma
    scrapers' descriptions), plus the first link's URL."""
    soup = BeautifulSoup(html_text, "html.parser")
    first_url: Optional[str] = None
    for a in soup.find_all("a", href=True):
        url = _unwrap_google_redirect(a["href"])
        first_url = first_url or url
        a.replace_with(f'<a href="{url}">{a.get_text(strip=True) or url}</a>')
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text().strip()
    return text or None, first_url


def _parse_event_block(
    lines: List[str], source: str, tz: ZoneInfo, display_url: str, keep_links: bool = False
) -> Optional[Event]:
    props = _block_props(lines)

    start_params, start_value = props.get("DTSTART", ("", ""))
    start = _parse_dt(start_value, start_params, tz) if start_value else None
    if not start:
        return None

    name = _unescape(props.get("SUMMARY", ("", ""))[1]).strip()
    if not name:
        return None

    end = None
    if "DTEND" in props:
        end_params, end_value = props["DTEND"]
        end = _parse_dt(end_value, end_params, tz)

    location = _unescape(props.get("LOCATION", ("", ""))[1]).strip() or None

    description = None
    source_url = display_url
    description_raw = props.get("DESCRIPTION", ("", ""))[1]
    if description_raw and keep_links:
        description, first_url = _description_with_links(_unescape(description_raw))
        source_url = first_url or display_url
    elif description_raw:
        text = BeautifulSoup(_unescape(description_raw), "html.parser").get_text(separator=" ", strip=True)
        description = text or None

    return Event(
        name=name,
        start_time=start,
        end_time=end,
        location=location,
        description=description,
        source_url=source_url,
        source=source,
    )


def _exdates(lines: List[str], tz: ZoneInfo) -> set[datetime]:
    """Every EXDATE (there can be several lines, each comma-separated)."""
    skipped: set[datetime] = set()
    for line in lines:
        parsed = _parse_prop(line)
        if not parsed or parsed[0] != "EXDATE":
            continue
        _, params, value = parsed
        for part in value.split(","):
            dt = _parse_dt(part.strip(), params, tz)
            if dt:
                skipped.add(dt)
    return skipped


def _expand_recurring(
    block: List[str],
    overridden: set[datetime],
    source: str,
    tz: ZoneInfo,
    display_url: str,
    until: datetime,
    keep_links: bool,
) -> List[Event]:
    """Expand a master VEVENT's RRULE into one Event per occurrence from now
    through `until`, skipping EXDATEs and occurrences that a separate
    RECURRENCE-ID VEVENT overrides (those are emitted on their own)."""
    template = _parse_event_block(block, source, tz, display_url, keep_links)
    if template is None:
        return []
    rrule_value = _block_props(block)["RRULE"][1]
    try:
        rule = rrulestr(rrule_value, dtstart=template.start_time)
    except (ValueError, TypeError) as exc:
        logger.warning(f"[{source}] unparseable RRULE {rrule_value!r} on {template.name!r}: {exc}")
        return []

    duration = (template.end_time - template.start_time) if template.end_time else None
    skip = _exdates(block, tz) | overridden
    now = datetime.now(tz=tz)
    events: List[Event] = []
    for occurrence in rule.between(now, until, inc=True):
        occurrence = occurrence.astimezone(tz)
        if occurrence in skip:
            continue
        events.append(Event(
            name=template.name,
            start_time=occurrence,
            end_time=occurrence + duration if duration else None,
            location=template.location,
            description=template.description,
            source_url=template.source_url,
            source=source,
        ))
    return events


def fetch_google_calendar_events(
    calendar_id: str,
    source: str,
    tz: ZoneInfo,
    display_url: str,
    expand_recurring: bool = False,
    horizon_days: int = 16,
    keep_links: bool = False,
) -> List[Event]:
    """Fetch upcoming events off a Google Calendar via its public iCal export.

    `calendar_id` is the same value used to address a calendar via the
    Calendar API ("someone@gmail.com" or the long
    "...@group.calendar.google.com" form), but here it's read through the
    public, unauthenticated ICS export instead — so this only works for
    calendars set to public, and needs no service-account share.

    By default a recurring event only yields its original DTSTART (which is
    usually in the past, so it's dropped). With `expand_recurring=True`, each
    RRULE is expanded into its occurrences over the next `horizon_days` days,
    honoring EXDATEs, per-occurrence edits (RECURRENCE-ID), and cancelled
    instances (STATUS:CANCELLED).

    With `keep_links=True`, links in the description are kept as inline
    <a href> tags instead of being flattened to their text, and the event's
    source_url becomes the first link (falling back to `display_url`).
    """
    url = _ICS_URL_TEMPLATE.format(calendar_id=quote(calendar_id))
    try:
        raw = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch calendar: {exc}")
        return []

    blocks: List[List[str]] = []
    current_block: Optional[List[str]] = None
    for line in _unfold(raw):
        if line == "BEGIN:VEVENT":
            current_block = []
            continue
        if line == "END:VEVENT":
            if current_block is not None:
                blocks.append(current_block)
            current_block = None
            continue
        if current_block is not None:
            current_block.append(line)

    now = datetime.now(tz=tz)
    until = now + timedelta(days=horizon_days)

    # Original start times of occurrences that have their own RECURRENCE-ID
    # VEVENT (an edited or cancelled single instance), keyed by series UID.
    overridden: dict[str, set[datetime]] = {}
    if expand_recurring:
        for block in blocks:
            props = _block_props(block)
            if "RECURRENCE-ID" not in props:
                continue
            rid_params, rid_value = props["RECURRENCE-ID"]
            rid = _parse_dt(rid_value, rid_params, tz)
            if rid:
                overridden.setdefault(props.get("UID", ("", ""))[1], set()).add(rid)

    events: List[Event] = []
    for block in blocks:
        props = _block_props(block)
        if expand_recurring:
            if props.get("STATUS", ("", ""))[1].upper() == "CANCELLED":
                continue
            if "RRULE" in props and "RECURRENCE-ID" not in props:
                uid = props.get("UID", ("", ""))[1]
                events.extend(
                    _expand_recurring(block, overridden.get(uid, set()), source, tz, display_url, until, keep_links)
                )
                continue
        event = _parse_event_block(block, source, tz, display_url, keep_links)
        if event and event.start_time >= now:
            events.append(event)

    logger.info(f"[{source}] parsed {len(events)} events")
    return events
