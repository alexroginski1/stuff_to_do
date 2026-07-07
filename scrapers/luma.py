from __future__ import annotations

import html
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
_EVENT_URL = "https://api2.luma.com/event/get?event_api_id={api_id}"
_TZ = ZoneInfo("America/Los_Angeles")


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


def _fetch_description(api_id: str) -> str:
    try:
        raw = fetch_html(_EVENT_URL.format(api_id=api_id))
        data = json.loads(raw)
        doc = data.get("description_mirror")
        if not doc:
            return ""
        return _render_doc(doc)
    except Exception as exc:
        logger.warning(f"Failed to fetch description for {api_id}: {exc}")
        return ""


def _extract_json(html: str) -> dict:
    """
    This endpoint returns raw JSON, not HTML.
    """
    return json.loads(html)


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
        description = _fetch_description(ev["api_id"]) if ev.get("api_id") else ""

        results.append(Event(
            name=name,
            start_time=start,
            end_time=end,
            location=location,
            description=description,
            source_url=url,
            source=source,
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
