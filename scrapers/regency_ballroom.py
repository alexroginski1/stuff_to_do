import json
import re

def _extract_json(html: str):
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});", html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def _parse_page(html: str) -> List[Event]:
    data = _extract_json(html)
    if not data:
        return []

    events = []
    for e in data.get("events", []):
        name = e.get("title")
        url = e.get("url")
        start = None

        if e.get("startDate"):
            start = datetime.fromisoformat(e["startDate"]).astimezone(TZ)

        events.append(Event(
            name=name,
            start_time=start,
            end_time=None,
            location="Regency Ballroom",
            description=None,
            source_url=url,
            source=SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return events