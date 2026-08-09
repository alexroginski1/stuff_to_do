from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import bleach
from flask import Flask, abort, request
from google.cloud import firestore
from markupsafe import Markup, escape

app = Flask(__name__)
_client = firestore.Client()
_COLLECTION = "sync_stats"
_EVENTS_COLLECTION = "event_snapshot"
_TZ = ZoneInfo("America/Los_Angeles")

# Event descriptions come from scraped third-party event pages and manually
# typed calendar entries, and are rendered verbatim on "/", so they're run
# through bleach rather than escaped, to strip anything beyond this safe
# formatting/link subset (e.g. a stray <script> tag on a source site) while
# still rendering as real HTML.
_DESCRIPTION_ALLOWED_TAGS = ["a", "b", "i", "strong", "em", "u", "br", "p", "ul", "ol", "li"]
_DESCRIPTION_ALLOWED_ATTRS = {"a": ["href"]}

# Source key -> display label, kept in sync with SOURCES in config/settings.py.
_SOURCE_LABELS = {
    "the_faight": "The Faight",
    "decentered_featured_events": "Decentered Featured Events",
    "funcheap": "SF Funcheap",
    "luma": "Luma",
    "decentered_community_events": "Decentered Community Events",
    "mannys": "Manny's: Community, Politics, and Culture",
    "the_sf_nook": "The SF Nook: SF Event Space",
    "luma_the_commons": "The Commons: Third Space",
    "luma_future_of_us": "Future of Us",
    "the_sf_contemplarium": "The SF Contemplarium",
    "luma_tiat": "TIAT Art and Tech",
    "partiful": "Partiful",
    "midnight_runners": "Midnight Runners SF",
    "november_project": "November Project SF",
}


def _parse_limit(default: int, max_value: int) -> int:
    """Parse the `limit` query param, rejecting anything non-numeric or out of range.

    A bare int(...) on unvalidated input raises on non-numeric values (e.g.
    ?limit=x) and silently accepts negatives, which Firestore's .limit()
    rejects with its own error — both surfaced as an unhandled 500.
    """
    raw = request.args.get("limit", default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        abort(400, description="limit must be an integer")
    if value < 1:
        abort(400, description="limit must be positive")
    return min(value, max_value)


def _format_pdt(dt) -> str:
    """Format a Firestore timestamp as e.g. 'June 5, 7:14 PM' in Pacific time."""
    if not dt:
        return ""
    return dt.astimezone(_TZ).strftime("%B %-d, %-I:%M %p")


def _sanitize_description(text: str | None) -> Markup:
    """Clean scraped/manual event-description HTML down to a safe formatting/link subset.

    Descriptions come from third-party event pages and from whatever anyone
    typed directly into a calendar event, so they're untrusted input even
    though this service is the only writer of the Firestore documents that
    carry them.
    """
    if not text:
        return Markup("")
    cleaned = bleach.clean(
        text,
        tags=_DESCRIPTION_ALLOWED_TAGS,
        attributes=_DESCRIPTION_ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    return Markup(cleaned)


@app.get("/")
def events_table():
    """Render the current event snapshot (app/event_snapshot_store.py), rewritten fresh by every scheduler run.

    This is the single source of truth for every event on the calendar,
    manual or parser-added — it's read straight from Firestore, so loading
    this page never calls the Google Calendar API.
    """
    limit = _parse_limit(default=2000, max_value=5000)

    query = (
        _client.collection(_EVENTS_COLLECTION)
        .order_by("start_time", direction=firestore.Query.ASCENDING)
        .limit(limit)
    )

    # Every document in a given scheduler run shares the same "timestamp"
    # (see app.event_snapshot_store.write_snapshot, which replaces the whole
    # collection each run), so the first doc's value is the run datetime.
    docs = [doc.to_dict() for doc in query.stream()]
    last_run = _format_pdt(docs[0].get("timestamp")) if docs else ""

    body_rows = "\n".join(
        f"<tr><td>{escape(d.get('title'))}</td>"
        f"<td>{_sanitize_description(d.get('description'))}</td>"
        f"<td>{_format_pdt(d.get('start_time'))}</td>"
        f"<td>{_format_pdt(d.get('end_time'))}</td>"
        f"<td>{escape(d.get('raw_location') or '')}</td>"
        f"<td>{escape(d.get('cleaned_location') or '')}</td>"
        f"<td>{escape(d.get('location_type') or '')}</td>"
        f"<td>{escape(d.get('calendar') or '')}</td>"
        f"<td>{escape(d.get('source_type') or '')}</td></tr>"
        for d in docs
    ) or '<tr><td colspan="7">No upcoming events</td></tr>'

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Stuff To Do — Events</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: left; vertical-align: top; }}
  td {{ white-space: pre-wrap; }}
  th {{ background: #f4f4f4; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  nav a {{ margin-right: 1rem; }}
</style>
</head>
<body>
<nav><a href="/">Events</a><a href="/sync-stats">Sync Stats</a></nav>
<h1>Events (Next 30 Days)</h1>
<p>Last scheduler run: {escape(last_run) or "unknown"}</p>
<table>
  <thead>
    <tr><th>Event Title</th><th>Event Description</th><th>Start</th><th>End</th>
        <th>Raw Location</th><th>Cleaned Location</th><th>Location Type</th>
        <th>Source Google Calendar</th><th>Manual / Automatic</th></tr>
  </thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
</body>
</html>"""


@app.get("/sync-stats")
def stats_table():
    """Render every scheduler run, across all calendars/sources, as one HTML table (newest first)."""
    limit = _parse_limit(default=200, max_value=1000)

    query = (
        _client.collection(_COLLECTION)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )

    rows = [
        (
            _format_pdt(d.get("timestamp")),
            d.get("calendar"),
            _SOURCE_LABELS.get(d.get("source"), d.get("source")),
            d.get("inserted"),
            d.get("deleted"),
            d.get("skipped"),
            d.get("errors"),
        )
        for d in (doc.to_dict() for doc in query.stream())
    ]
    body_rows = "\n".join(
        f"<tr><td>{escape(job_dt)}</td><td>{escape(cal)}</td><td>{escape(src)}</td>"
        f"<td>{ins}</td><td>{det}</td><td>{skp}</td><td>{err}</td></tr>"
        for job_dt, cal, src, ins, det, skp, err in rows
    ) or '<tr><td colspan="7">No data yet</td></tr>'

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Stuff To Do — Sync Stats</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 960px; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: right; }}
  th, td:nth-child(1), td:nth-child(2), td:nth-child(3) {{ text-align: left; }}
  th {{ background: #f4f4f4; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  nav a {{ margin-right: 1rem; }}
</style>
</head>
<body>
<nav><a href="/">Events</a><a href="/sync-stats">Sync Stats</a></nav>
<h1>Sync Stats</h1>
<table>
  <thead>
    <tr><th>Job Datetime</th><th>Calendar</th><th>Source</th>
        <th>Inserted</th><th>Deleted</th><th>Skipped</th><th>Errors</th></tr>
  </thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
</body>
</html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
