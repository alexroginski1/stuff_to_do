from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def fetch_html(url: str, headers: Optional[dict] = None, timeout: int = 20) -> str:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = _session.get(url, headers=merged, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Eventbrite API helpers
# ---------------------------------------------------------------------------

_EVENTBRITE_TZ = ZoneInfo("America/Los_Angeles")
_EVENTBRITE_API_BASE = "https://www.eventbriteapi.com/v3"

_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tokens", ".env")


def _load_env_file() -> None:
    try:
        with open(_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
    except FileNotFoundError:
        pass


_load_env_file()


def _eventbrite_get(path: str, params: Optional[dict] = None) -> dict:
    token = os.environ.get("EVENTBRITE_API_TOKEN", "")
    resp = _session.get(
        f"{_EVENTBRITE_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=10,
    )
    if not resp.ok:
        logger.error(f"Eventbrite API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def _parse_eventbrite_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_EVENTBRITE_TZ)
    except Exception:
        return None


def _eventbrite_structured_description(event_id: str) -> Optional[str]:
    """Fall back to the structured-content endpoint for events whose classic
    `description.text` is empty (organizers using Eventbrite's newer
    block-based description editor don't populate that field)."""
    try:
        data = _eventbrite_get(f"/events/{event_id}/structured_content/")
    except Exception as exc:
        logger.warning(f"Failed to fetch structured content for event {event_id}: {exc}")
        return None

    texts = []
    for module in data.get("modules", []):
        if module.get("type") != "text":
            continue
        html = ((module.get("data") or {}).get("body") or {}).get("text")
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["p", "li", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
            tag.insert_after("\n")
        text = soup.get_text().strip()
        if text:
            texts.append(text)

    return "\n\n".join(texts) or None


def _parse_eventbrite_event(e: dict, source: str) -> Optional["Event"]:
    from app.event_model import Event

    if e.get("status") != "live":
        return None

    name = (e.get("name") or {}).get("text")
    start = _parse_eventbrite_dt((e.get("start") or {}).get("utc"))

    if not name or not start or start < datetime.now(tz=_EVENTBRITE_TZ):
        return None

    end = _parse_eventbrite_dt((e.get("end") or {}).get("utc"))

    venue = e.get("venue") or {}
    location_parts = [
        venue.get("name"),
        (venue.get("address") or {}).get("localized_address_display"),
    ]
    location = ", ".join([p for p in location_parts if p]) or None

    description = (e.get("description") or {}).get("text")
    if not description and e.get("id"):
        description = _eventbrite_structured_description(e["id"])

    return Event(
        name=name.strip(),
        start_time=start,
        end_time=end,
        location=location,
        description=description,
        source_url=e.get("url"),
        source=source,
    )


def fetch_eventbrite_organizer_events(
    organizer_id: str, source: str, max_pages: int = 10
) -> List["Event"]:
    """Fetch all live upcoming events for an Eventbrite organizer."""
    all_events: list = []
    for page in range(1, max_pages + 1):
        try:
            data = _eventbrite_get(
                f"/organizers/{organizer_id}/events/", {"page": page, "expand": "venue,description"}
            )
        except Exception as exc:
            logger.warning(f"[{source}] failed to fetch Eventbrite page {page}: {exc}")
            break

        page_events = [
            ev for e in data.get("events", [])
            if (ev := _parse_eventbrite_event(e, source)) is not None
        ]

        if not page_events:
            logger.info(f"[{source}] no events on Eventbrite page {page}, stopping")
            break

        all_events.extend(page_events)
        logger.info(f"[{source}] Eventbrite page {page}: {len(page_events)} events")

        if not data.get("pagination", {}).get("has_more_items"):
            break

    return all_events


def _eventbrite_event_id(url: str) -> Optional[str]:
    """Extract the numeric event ID from an Eventbrite URL."""
    m = re.search(r"(?:^|[-/])(\d+)(?:/)?$", url.split("?")[0].rstrip("/"))
    return m.group(1) if m else None


def fetch_eventbrite_price(url: str) -> Optional[str]:
    """Return a formatted price string for an Eventbrite event using the API.

    Shows every distinct ticket price, ascending, slash-separated (e.g.
    "$17/$28/$39") rather than just the cheapest, since ticket tiers are
    often meaningfully different (e.g. early bird vs. door price).
    """
    event_id = _eventbrite_event_id(url)
    if not event_id:
        logger.warning(f"Could not extract Eventbrite event ID from {url}")
        return None
    try:
        data = _eventbrite_get(f"/events/{event_id}/ticket_classes/")
        visible = [tc for tc in data.get("ticket_classes", []) if not tc.get("hidden")]
        if not visible:
            return None

        # Free tickets have cost=None and free=True.
        def _cents(tc: dict) -> int:
            cost = tc.get("cost")
            return cost["value"] if cost else 0

        distinct_cents = sorted({_cents(tc) for tc in visible})
        labels = ["Free" if cents == 0 else f"${round(cents / 100)}" for cents in distinct_cents]
        return "/".join(labels)
    except Exception as e:
        logger.warning(f"Failed to fetch Eventbrite price for {url}: {e}")
    return None


# ---------------------------------------------------------------------------
# Mobilize.us helpers
# ---------------------------------------------------------------------------

_MOBILIZE_DATA_RE = re.compile(r"window\.__MLZ_EMBEDDED_DATA__\s*=\s*(\{.*?\});\s*\n")


def _mobilize_get_page(org_slug: str, page: int, tag_ids: Optional[List[str]] = None) -> dict:
    params: dict = {"page": page}
    if tag_ids:
        params["tag_ids"] = tag_ids
    resp = _session.get(
        f"https://www.mobilize.us/{org_slug}/",
        headers=_DEFAULT_HEADERS,
        params=params,
        timeout=20,
    )
    resp.raise_for_status()
    match = _MOBILIZE_DATA_RE.search(resp.text)
    if not match:
        raise RuntimeError(f"__MLZ_EMBEDDED_DATA__ not found on Mobilize page: {resp.url}")
    return json.loads(match.group(1))["data"]


def _mobilize_location(e: dict) -> Optional[str]:
    if e.get("is_virtual"):
        return None
    parts = [e.get("location_name"), e.get("address_line1"), e.get("city")]
    return ", ".join([p for p in parts if p]) or None


def fetch_mobilize_org_events(
    org_slug: str, source: str, tag_ids: Optional[List[str]] = None, max_pages: int = 10
) -> List["Event"]:
    """Fetch upcoming events for a Mobilize.us organization page, one Event per timeslot
    (recurring events like weekly cleanups list multiple timeslots under a single event)."""
    from app.event_model import Event

    events: List[Event] = []
    now = datetime.now(timezone.utc)
    page = 1

    while page <= max_pages:
        try:
            data = _mobilize_get_page(org_slug, page, tag_ids)
        except Exception as exc:
            logger.warning(f"[{source}] failed to fetch Mobilize page {page}: {exc}")
            break

        raw_events = data.get("events", [])
        for e in raw_events:
            name = e.get("name")
            event_id = e.get("id")
            if not name or not event_id:
                continue

            location = _mobilize_location(e)
            description = e.get("description")
            url = f"https://www.mobilize.us/{org_slug}/event/{event_id}/"

            for slot in e.get("times") or []:
                start = parse_iso_datetime(slot["start"]) if slot.get("start") else None
                if not start or start < now:
                    continue
                end = parse_iso_datetime(slot["end"]) if slot.get("end") else None
                events.append(Event(
                    name=name.strip(),
                    start_time=start,
                    end_time=end,
                    location=location,
                    description=description,
                    source_url=url,
                    source=source,
                ))

        num_pages = (data.get("paging_info") or {}).get("num_pages", 1)
        logger.info(f"[{source}] Mobilize page {page}/{num_pages}: {len(raw_events)} events")
        if page >= num_pages:
            break
        page += 1

    return events


# ---------------------------------------------------------------------------
# Squarespace Events collection helpers
# ---------------------------------------------------------------------------

_SQUARESPACE_TZ = ZoneInfo("America/Los_Angeles")


def _squarespace_location(loc: Optional[dict]) -> Optional[str]:
    if not loc:
        return None
    parts = [loc.get("addressLine1") or loc.get("addressTitle"), loc.get("addressLine2")]
    return ", ".join([p for p in parts if p]) or None


def _squarespace_dt(ms: Optional[int]) -> Optional[datetime]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(_SQUARESPACE_TZ)


def fetch_squarespace_events(collection_url: str, source: str) -> List["Event"]:
    """Fetch upcoming events from a Squarespace Events-collection page via its
    built-in `?format=json` endpoint (every Squarespace collection page
    supports this; undocumented but stable)."""
    from app.event_model import Event

    try:
        raw = fetch_html(f"{collection_url.rstrip('/')}?format=json")
        data = json.loads(raw)
    except Exception as exc:
        logger.warning(f"[{source}] fetch failed: {exc}")
        return []

    base = urlsplit(collection_url)
    events: List[Event] = []
    for item in data.get("upcoming", []):
        name = item.get("title")
        start = _squarespace_dt(item.get("startDate"))
        if not name or not start:
            continue

        full_url = item.get("fullUrl")
        source_url = f"{base.scheme}://{base.netloc}{full_url}" if full_url else collection_url

        excerpt = item.get("excerpt")
        description = BeautifulSoup(excerpt, "html.parser").get_text("\n", strip=True) if excerpt else None

        events.append(Event(
            name=html.unescape(name).strip(),
            start_time=start,
            end_time=_squarespace_dt(item.get("endDate")),
            location=_squarespace_location(item.get("location")),
            description=description or None,
            source_url=source_url,
            source=source,
        ))

    logger.info(f"[{source}] parsed {len(events)} events")
    return events


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def parse_iso_datetime(s: str):
    """Parse an ISO 8601 datetime string into a timezone-aware datetime."""
    return dtparser.parse(s)


def format_readable_dt(dt: datetime) -> str:
    """Format a datetime for human-readable logging, e.g. 'Jul 01, 2026 03:00 PM PDT'."""
    return dt.strftime("%b %d, %Y %I:%M %p %Z").strip()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def emit_metric(event_type: str, **fields) -> None:
    """Print a structured JSON entry to stdout for Cloud Logging metric extraction."""
    import sys
    payload = {"event_type": event_type, **fields}
    print(json.dumps(payload), file=sys.stdout, flush=True)
