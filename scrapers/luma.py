from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from pathlib import Path

from app.event_model import Event
from app.utils import fetch_html

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).stem
_URL = "https://api2.luma.com/discover/get-paginated-events?discover_place_api_id=discplace-BDj7GNbGlsF7Cka&pagination_limit=50"
_TZ = ZoneInfo("America/Los_Angeles")


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ)
    except Exception:
        return None


def _extract_json(html: str) -> dict:
    """
    This endpoint returns raw JSON, not HTML.
    """
    return json.loads(html)


def _format_price(entry: dict) -> Optional[str]:
    """
    NOTE: ticket_info lives on `entry`, not `event`
    """
    ticket_info = entry.get("ticket_info") or {}

    # 1. Free events
    if ticket_info.get("is_free"):
        return "Free"

    price = ticket_info.get("price") or {}

    # 2. Exact price
    cents = price.get("cents")
    currency = price.get("currency")

    if cents is not None and currency == "usd":
        dollars = cents / 100
        return f"${int(dollars)}" if dollars.is_integer() else f"${dollars:.2f}"

    # 3. Max price fallback
    max_price = ticket_info.get("max_price")
    if isinstance(max_price, dict):
        cents = max_price.get("cents")
        currency = max_price.get("currency")
        if cents is not None and currency == "usd":
            dollars = cents / 100
            return (
                f"Up to ${int(dollars)}"
                if dollars.is_integer()
                else f"Up to ${dollars:.2f}"
            )

    # 4. If ticket_info exists but no clear price
    if ticket_info:
        return "Paid"

    return None


def _build_description(url: str, price_str: Optional[str]) -> str:
    parts = []

    if price_str:
        parts.append(f"Price: {price_str}")

    return "\n".join(parts)


def _parse_events(data: dict, source: str, sf_only: bool = False) -> List[Event]:
    results: List[Event] = []

    entries = data.get("entries", [])
    for entry in entries:
        ev = entry.get("event") or {}
        geo = ev.get("geo_address_info") or {}

        # Optional SF filter
        if sf_only:
            city = (geo.get("city") or "").lower()
            if "san francisco" not in city:
                continue

        name = ev.get("name")
        start = _parse_dt(ev.get("start_at"))
        end = _parse_dt(ev.get("end_at"))
        url_slug = ev.get("url")

        if not name or not start:
            continue

        url = f"https://luma.com/{url_slug}" if url_slug else ""
        location = geo.get("sublocality") or geo.get("city")

        # ✅ FIX: pass entry (not ev)
        price_str = _format_price(entry)

        # Append price to title
        if price_str:
            name = f"{name} ({price_str})"

        # Build description
        description = _build_description(url, price_str)

        results.append(Event(
            name=name,
            start_time=start,
            end_time=end,
            location=location,
            description=description,
            source_url=url,
            source=source,
            unique_key=Event.build_unique_key(name, start),
        ))

    return results


def fetch_luma_events(url: str, source: str, sf_only: bool = False) -> List[Event]:
    try:
        raw = fetch_html(url)
    except Exception as exc:
        logger.warning(f"[{source}] fetch failed: {exc}")
        return []

    try:
        data = _extract_json(raw)
        events = _parse_events(data, source, sf_only=sf_only)
        logger.info(f"[{source}] parsed {len(events)} events")
        return events
    except Exception as exc:
        logger.exception(f"[{source}] parse failed: {exc}")
        return []


def fetch_events() -> List[Event]:
    return fetch_luma_events(_URL, _SOURCE, sf_only=True)