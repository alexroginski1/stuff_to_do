from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_BASE_URL = "https://sfpl.org/events"
_ICS_BASE_URL = "https://sfpl.org/sfpl-events/add-to-calendar"
_TZ = ZoneInfo("America/Los_Angeles")

# Cap on listing pages fetched per (topic, audience) query, and how far out
# (by listing date, which is unambiguous unlike the listing's AM/PM-less time
# range) to keep paginating. Results are sorted chronologically, so as soon
# as one row is past the horizon, it and everything after it (this page and
# every later page) is dropped. Small buffer over the sync engine's 14-day
# lookahead (app/sync_engine.py _LOOKAHEAD_DAYS) so nothing near the cutoff
# gets missed to a timezone/date edge.
_MAX_PAGES = 6
_HORIZON_DAYS = 16

# (topic_id, audience_id) query pairs mirroring the site's own filter links
# for each subcategory. "Community & Neighborhood" is the only one of these
# that also includes the "All Ages" audience on top of "Adults" — every other
# category is Adults-only per the source URLs.
_QUERIES: List[tuple[str, str]] = [
    ("468", "1082"),  # Community & Neighborhood - All Ages
    ("468", "25"),  # Community & Neighborhood - Adults
    ("394", "25"),  # Book Clubs
    ("452", "25"),  # Dance & Music
    ("386", "25"),  # Environment & Nature
    ("540", "25"),  # Health & Wellness
    ("553", "25"),  # Gaming
    ("1106", "25"),  # Local History
    ("537", "25"),  # Poetry
    ("569", "25"),  # Performance
    ("564", "25"),  # Read & Write
]

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _listing_url(topic: str, audience: str, page: int) -> str:
    return (
        f"{_BASE_URL}?field_event_topic_target_id={topic}"
        f"&field_event_audience_target_id={audience}&page={page}"
    )


def _parse_listing_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_listing(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for article in soup.select("article.event"):
        title_link = article.select_one(".event__title a")
        detail_href = article.get("about")
        quickview = article.select_one("a.btn--quickview")
        if title_link is None or not detail_href or quickview is None:
            continue
        name = title_link.get_text(strip=True)
        # No dedicated "canceled" CSS class on the listing card — the only
        # signal is this literal prefix the site puts on the title itself.
        if name.lower().startswith("canceled:"):
            continue
        node_match = re.search(r"/quickview/(\d+)", quickview.get("href", ""))
        if not node_match:
            continue
        date_span = article.select_one(".event__date .date-display-range")
        rows.append(
            {
                "name": name,
                "url": urljoin(_BASE_URL, detail_href),
                "node_id": node_match.group(1),
                "date": _parse_listing_date(date_span.get_text(strip=True)) if date_span else None,
            }
        )
    return rows


def _fetch_query_rows(topic: str, audience: str, cutoff: date) -> List[dict]:
    rows: List[dict] = []
    for page in range(_MAX_PAGES):
        try:
            html = fetch_html(_listing_url(topic, audience, page))
        except Exception as exc:
            logger.warning(f"[{_SOURCE}] failed to fetch topic={topic} audience={audience} page={page}: {exc}")
            break
        page_rows = _parse_listing(html)
        if not page_rows:
            break

        reached_horizon = False
        for row in page_rows:
            if row["date"] and row["date"] > cutoff:
                reached_horizon = True
                break
            rows.append(row)
        if reached_horizon:
            break
    return rows


def _ics_field(text: str, name: str) -> Optional[str]:
    m = re.search(rf"^{name}:(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _parse_ics_dt(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fetch_ics(node_id: str) -> Optional[dict]:
    """The site's own "Add to My Calendar" feed for one event: the only place
    that gives an unambiguous (UTC) start/end, since the listing and detail
    pages both show times as bare "10:00 - 2:00" with no AM/PM marker."""
    try:
        text = fetch_html(f"{_ICS_BASE_URL}/{node_id}").replace("\r\n", "\n")
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch ics for node {node_id}: {exc}")
        return None

    dtstart = _ics_field(text, "DTSTART")
    if not dtstart:
        return None
    start = _parse_ics_dt(dtstart)
    if start is None:
        return None
    dtend = _ics_field(text, "DTEND")
    end = _parse_ics_dt(dtend) if dtend else None

    return {
        "start": start,
        "end": end,
        "summary": _ics_field(text, "SUMMARY"),
        "description_html": _ics_field(text, "DESCRIPTION"),
        "location": _ics_field(text, "LOCATION"),
    }


def _html_to_text(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    parts = [" ".join(p.get_text(" ", strip=True).split()) for p in soup.find_all("p")]
    parts = [p for p in parts if p]
    if parts:
        return "\n\n".join(parts)
    text = " ".join(soup.get_text(" ", strip=True).split())
    return text or None


def _extract_address(soup: BeautifulSoup) -> Optional[str]:
    # The page also embeds a "find your branch" widget listing every SFPL
    # location's address, so the lookup has to be scoped to the event's own
    # address block (.event__address) — an unscoped page-wide selector would
    # just grab that widget's first entry (always Main Library) instead.
    # Regular branches use field--name-field-address; events at an outside
    # venue (a park, a playground) use field--name-field-external-venues-address
    # instead, with the same inner markup.
    container = soup.select_one(".event__address")
    if container is None:
        return None
    field = container.select_one(".field--name-field-address, .field--name-field-external-venues-address")
    if field is None:
        return None
    line1 = field.select_one(".address-line1")
    locality = field.select_one(".locality")
    region = field.select_one(".administrative-area")
    postal = field.select_one(".postal-code")
    if line1 is None or locality is None:
        return None
    parts = [
        line1.get_text(strip=True),
        locality.get_text(strip=True),
        region.get_text(strip=True) if region else None,
        postal.get_text(strip=True) if postal else None,
    ]
    return ", ".join(p for p in parts if p) or None


def _fetch_detail_address(url: str) -> Optional[str]:
    try:
        html = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{_SOURCE}] failed to fetch detail {url}: {exc}")
        return None
    return _extract_address(BeautifulSoup(html, "html.parser"))


def fetch_events() -> List[Event]:
    cutoff = datetime.now(tz=_TZ).date() + timedelta(days=_HORIZON_DAYS)

    rows: Dict[str, dict] = {}
    for topic, audience in _QUERIES:
        for row in _fetch_query_rows(topic, audience, cutoff):
            rows.setdefault(row["url"], row)

    events: List[Event] = []
    for row in rows.values():
        ics = _fetch_ics(row["node_id"])
        if not ics:
            continue

        # "Bookmobiles / Mobile Outreach" and similar generic ICS locations
        # are just the site's taxonomy bucket for the branch — the specific
        # event's own detail page still carries a real venue address (e.g. a
        # particular park), so it's always worth checking rather than
        # trusting the ICS location text. _extract_address itself returns
        # None for genuinely address-less cases like "Virtual Library".
        location = _fetch_detail_address(row["url"])

        events.append(
            Event(
                name=ics["summary"] or row["name"],
                start_time=ics["start"],
                end_time=ics["end"],
                location=location,
                description=_html_to_text(ics["description_html"]),
                source_url=row["url"],
                source=_SOURCE,
                location_verified=True,
            )
        )

    logger.info(f"[{_SOURCE}] fetched {len(events)} events")
    return events
