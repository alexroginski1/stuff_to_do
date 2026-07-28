from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import google.auth
from flask import Flask, request
from google.cloud import firestore
from googleapiclient.discovery import build
from markupsafe import escape

app = Flask(__name__)
_client = firestore.Client()
_COLLECTION = "sync_stats"
_TZ = ZoneInfo("America/Los_Angeles")

_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
_MANUAL_LABEL = "Manually Added Events"
_calendar_service = None

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
}

# Calendar display name -> Google Calendar ID, kept in sync with CALENDAR_IDS in config/settings.py.
_CALENDAR_IDS = {
    "SF Arts/Culture": "7f66e10ca74622780fdf0db852f0dc8e4be2272cf206bfc8cf83f2eaefc8abdf@group.calendar.google.com",
    "SF Community": "c40ce35591588f6a8cf1d14e96f4ec215f2d812857382a0fb7253eabea1a0154@group.calendar.google.com",
    "SF Fun Cheap": "60a19fdad14c75dc604082f022416e48c2d30dc440502a5e80bf410d32570d1d@group.calendar.google.com",
    "SF Partiful": "9d7c77c609ffc954909e2a0cb72e2c2b5029048fe87d0ba6a035ccac18e1472a@group.calendar.google.com",
    "SF Tech": "45264416fab34dddf5fff1ca40931d59a13f865ec441d158030be512b30d6b15@group.calendar.google.com",
    "SF Bars": "9c8685a68b697409a5bffa6ce3011651930fa18572dad9ef435215753a43de22@group.calendar.google.com",
    "SF Dancing": "704367c0fe7ec0383a79ab3bd6a4388d8c867642120862ffa11191fdb27e407f@group.calendar.google.com",
}


def _get_calendar_service():
    """Build (and cache) a read-only Calendar API client using the service's own ADC.

    Requires each calendar in _CALENDAR_IDS to be shared with this Cloud Run
    service's account, granting at least "See all event details".
    """
    global _calendar_service
    if _calendar_service is None:
        creds, _ = google.auth.default(scopes=_CALENDAR_SCOPES)
        _calendar_service = build("calendar", "v3", credentials=creds)
    return _calendar_service


def _count_events_by_source(service, calendar_id: str) -> dict[str, int]:
    """Return {source label: count} for events in the next 7 days on `calendar_id`.

    Events without a `source` private extended property (i.e. not created by
    the parser, such as events added directly on the calendar) are grouped
    under _MANUAL_LABEL.
    """
    counts: dict[str, int] = {}
    now = datetime.now(tz=timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=7)).isoformat()
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            singleEvents=True,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=2500,
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            source = item.get("extendedProperties", {}).get("private", {}).get("source")
            label = _SOURCE_LABELS.get(source, source) if source else _MANUAL_LABEL
            counts[label] = counts.get(label, 0) + 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return counts


def _format_pdt(dt) -> str:
    """Format a Firestore timestamp as e.g. 'June 5, 7:14 PM' in Pacific time."""
    if not dt:
        return ""
    return dt.astimezone(_TZ).strftime("%B %-d, %-I:%M %p")


@app.get("/")
def stats_table():
    """Render every scheduler run, across all calendars/sources, as one HTML table (newest first)."""
    limit = min(int(request.args.get("limit", 200)), 1000)

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
<nav><a href="/">Sync Stats</a><a href="/by-source">Events by Source</a></nav>
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


@app.get("/by-source")
def events_by_source():
    """Render current upcoming event counts per calendar, broken down by source."""
    service = _get_calendar_service()

    body_rows = ""
    for cal_name, cal_id in _CALENDAR_IDS.items():
        counts = _count_events_by_source(service, cal_id)
        total = sum(counts.values())
        if not counts:
            body_rows += f'<tr><td>{escape(cal_name)}</td><td colspan="2">No upcoming events</td></tr>\n'
            continue
        for source_label, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            body_rows += f"<tr><td>{escape(cal_name)}</td><td>{escape(source_label)}</td><td>{count}</td></tr>\n"
        body_rows += f'<tr class="total"><td>{escape(cal_name)}</td><td>Total</td><td>{total}</td></tr>\n'

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Stuff To Do — Events by Source</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: right; }}
  th, td:nth-child(1), td:nth-child(2) {{ text-align: left; }}
  th {{ background: #f4f4f4; }}
  tr.total {{ font-weight: bold; background: #eef; }}
  nav a {{ margin-right: 1rem; }}
</style>
</head>
<body>
<nav><a href="/">Sync Stats</a><a href="/by-source">Events by Source</a></nav>
<h1>Events by Source (Next 7 Days)</h1>
<table>
  <thead>
    <tr><th>Calendar</th><th>Source</th><th>Events</th></tr>
  </thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
</body>
</html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
