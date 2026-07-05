from __future__ import annotations

import os

from flask import Flask, jsonify, request
from google.cloud import firestore
from markupsafe import escape

app = Flask(__name__)
_client = firestore.Client()
_COLLECTION = "sync_stats"

_FIELDS = ("calendar", "source", "inserted", "deleted", "skipped", "errors")


def _latest_stats_data() -> dict:
    latest = list(
        _client.collection(_COLLECTION)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    if not latest:
        return {"run_id": None, "calendars": {}}

    run_id = latest[0].get("run_id")
    docs = _client.collection(_COLLECTION).where("run_id", "==", run_id).stream()

    calendars: dict[str, list[dict]] = {}
    for doc in docs:
        d = doc.to_dict()
        calendars.setdefault(d["calendar"], []).append({f: d[f] for f in _FIELDS if f != "calendar"})

    return {"run_id": run_id, "calendars": calendars}


@app.get("/stats")
def latest_stats():
    """Return every calendar/source's stats from the most recent scheduler run."""
    return jsonify(_latest_stats_data())


@app.get("/stats/table")
def stats_table():
    """Render the most recent scheduler run as an HTML table, for viewing in a browser."""
    data = _latest_stats_data()

    rows = [
        (calendar, s["source"], s["inserted"], s["deleted"], s["skipped"], s["errors"])
        for calendar, sources in sorted(data["calendars"].items())
        for s in sources
    ]
    body_rows = "\n".join(
        f"<tr><td>{escape(cal)}</td><td>{escape(src)}</td>"
        f"<td>{ins}</td><td>{det}</td><td>{skp}</td><td>{err}</td></tr>"
        for cal, src, ins, det, skp, err in rows
    ) or '<tr><td colspan="6">No data yet</td></tr>'

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Stuff To Do — Sync Stats</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: right; }}
  th, td:nth-child(1), td:nth-child(2) {{ text-align: left; }}
  th {{ background: #f4f4f4; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  caption {{ text-align: left; margin-bottom: 0.5rem; color: #666; }}
</style>
</head>
<body>
<h1>Sync Stats</h1>
<table>
  <caption>Run: {escape(data["run_id"] or "no runs yet")}</caption>
  <thead>
    <tr><th>Calendar</th><th>Source</th><th>Inserted</th><th>Deleted</th><th>Skipped</th><th>Errors</th></tr>
  </thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
</body>
</html>"""


@app.get("/stats/history")
def history():
    """Return past runs, optionally filtered by calendar and/or source."""
    calendar = request.args.get("calendar")
    source = request.args.get("source")
    limit = min(int(request.args.get("limit", 50)), 500)

    query = _client.collection(_COLLECTION)
    if calendar:
        query = query.where("calendar", "==", calendar)
    if source:
        query = query.where("source", "==", source)
    query = query.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)

    runs = [
        {"run_id": d.get("run_id"), **{f: d.get(f) for f in _FIELDS}}
        for d in (doc.to_dict() for doc in query.stream())
    ]
    return jsonify({"count": len(runs), "runs": runs})


@app.get("/")
def index():
    return jsonify({
        "endpoints": {
            "/stats": "latest scheduler run, grouped by calendar (JSON)",
            "/stats/table": "latest scheduler run, as an HTML table",
            "/stats/history?calendar=&source=&limit=": "past runs, most recent first (JSON)",
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
