from __future__ import annotations

import calendar
import html
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, List, Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from app.event_model import Event

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
_SC_RE = re.compile(r"""class=['"]evo_cal_data['"] data-sc="([^"]*)\"""")
_NONCE_RE = re.compile(r'"n":"([0-9a-f]+)"')


def _flatten(prefix: str, obj, out: list) -> None:
    """Encode nested dicts the way jQuery.ajax form-encodes them (a[b][c]=v)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}[{k}]", v, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten(f"{prefix}[{i}]", v, out)
    else:
        out.append((prefix, "" if obj is None else str(obj)))


def _months(start: date, end: date) -> Iterator[tuple[int, int]]:
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _month_events(session: requests.Session, site: str, sc: dict, nonce: str, year: int, month: int) -> List[dict]:
    """One month of the calendar's event JSON via EventON's init-load endpoint.

    This is the same request EventON's own eventon_script.js makes on page
    load: the calendar's shortcode settings (from the page's
    `.evo_cal_data[data-sc]`), with the month swapped in, plus the page's
    public nonce. The response carries a `json` list per calendar with
    every occurrence in that month (repeating events already expanded).
    """
    sc = dict(sc)
    last_day = calendar.monthrange(year, month)[1]
    sc.update(
        fixed_month=str(month),
        fixed_year=str(year),
        focus_start_date_range=str(calendar.timegm((year, month, 1, 0, 0, 0))),
        focus_end_date_range=str(calendar.timegm((year, month, last_day, 23, 59, 59))),
    )
    data = [("nonce", nonce)]
    _flatten("cals[cal][sc]", sc, data)
    resp = session.post(f"{site}/?evo-ajax=eventon_init_load", data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") == "bad":
        raise RuntimeError(f"EventON rejected request: {payload.get('msg')}")
    return ((payload.get("cals") or {}).get("cal") or {}).get("json") or []


def _post_details(session: requests.Session, site: str, ids: List[int]) -> dict[int, dict]:
    """{post id: {"link", "description"}} from WordPress's REST API (EventON's
    `ajde_events` post type), since the calendar JSON has neither."""
    details: dict[int, dict] = {}
    for i in range(0, len(ids), 100):
        chunk = ",".join(str(x) for x in ids[i:i + 100])
        resp = session.get(
            f"{site}/wp-json/wp/v2/ajde_events",
            params={"include": chunk, "per_page": 100, "_fields": "id,link,content"},
            timeout=30,
        )
        resp.raise_for_status()
        for post in resp.json():
            body = BeautifulSoup((post.get("content") or {}).get("rendered") or "", "html.parser")
            text = body.get_text("\n", strip=True)
            details[post["id"]] = {"link": post.get("link"), "description": text or None}
    return details


def _pm(event: dict, key: str) -> Optional[str]:
    value = (event.get("event_pmv") or {}).get(key)
    return value[0] if isinstance(value, list) and value else value


def fetch_eventon_events(
    calendar_url: str,
    source: str,
    tz: ZoneInfo,
    location: Optional[str] = None,
    horizon_days: int = 16,
) -> List[Event]:
    """Upcoming events from a WordPress site's EventON calendar page.

    EventON's `event_start_unix`/`event_end_unix` are the event's local
    wall-clock time encoded as if it were UTC (the plugin renders them with
    gmdate), so they're read as UTC and then re-labelled with `tz` rather
    than converted.

    `location`, if given, is used for every event as a verified address
    (EventON venues are optional and single-venue sites usually leave them
    blank).
    """
    parts = urlsplit(calendar_url)
    site = f"{parts.scheme}://{parts.netloc}"
    session = requests.Session()
    session.headers.update(_HEADERS)

    try:
        page = session.get(calendar_url, timeout=30)
        page.raise_for_status()
        sc_match, nonce_match = _SC_RE.search(page.text), _NONCE_RE.search(page.text)
        if not sc_match or not nonce_match:
            raise RuntimeError("EventON calendar data/nonce not found on page")
        sc = json.loads(html.unescape(sc_match.group(1)))
        nonce = nonce_match.group(1)
    except Exception as exc:
        logger.warning(f"[{source}] failed to load calendar page: {exc}")
        return []

    now = datetime.now(tz=tz)
    until = now + timedelta(days=horizon_days)
    raw_events: List[dict] = []
    for year, month in _months(now.date(), until.date()):
        try:
            raw_events.extend(_month_events(session, site, sc, nonce, year, month))
        except Exception as exc:
            logger.warning(f"[{source}] failed to fetch {year}-{month:02d}: {exc}")

    try:
        details = _post_details(session, site, sorted({e["event_id"] for e in raw_events if e.get("event_id")}))
    except Exception as exc:
        logger.warning(f"[{source}] failed to fetch event details: {exc}")
        details = {}

    def wall_clock(ts) -> datetime:
        return datetime.fromtimestamp(int(ts), timezone.utc).replace(tzinfo=tz)

    seen: set[tuple] = set()
    events: List[Event] = []
    for raw in raw_events:
        try:
            if _pm(raw, "_status") == "cancelled" or _pm(raw, "evcal_allday") == "yes":
                continue
            start = wall_clock(raw["event_start_unix"])
            end = wall_clock(raw["event_end_unix"]) if raw.get("event_end_unix") else None
            if end and end <= start:
                end = None
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(f"[{source}] skipping malformed event {raw.get('event_id')!r}: {exc}")
            continue
        key = (raw.get("event_id"), start)
        if key in seen or (end or start) < now or not raw.get("event_title"):
            continue
        seen.add(key)
        detail = details.get(raw.get("event_id"), {})
        event = Event(
            name=html.unescape(raw["event_title"]),
            start_time=start,
            end_time=end,
            location=location,
            description=detail.get("description"),
            source_url=detail.get("link") or calendar_url,
            source=source,
        )
        if location:
            event.location_verified = True
        events.append(event)

    logger.info(f"[{source}] parsed {len(events)} events")
    return events
