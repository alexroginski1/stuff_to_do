from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from flask import Flask, request
from google.cloud import firestore
from markupsafe import escape

app = Flask(__name__)
_client = firestore.Client()
_COLLECTION = "sync_stats"
_TZ = ZoneInfo("America/Los_Angeles")

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
    "luma_tiat": "TIAT Art and Tech",
    "partiful": "Partiful",
}


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
</style>
</head>
<body>
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
