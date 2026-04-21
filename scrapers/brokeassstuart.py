def _extract_events(html: str):
    import json, re

    matches = re.findall(r'window\.__DATA__\s*=\s*(\{.*?\});', html)
    for m in matches:
        try:
            return json.loads(m)
        except Exception:
            continue
    return None


def _parse_page(html: str) -> List[Event]:
    data = _extract_events(html)
    if not data:
        return []

    events: List[Event] = []

    for e in data.get("events", []):
        name = e.get("title")
        url = e.get("url")

        start = None
        if e.get("start_time"):
            start = datetime.fromisoformat(e["start_time"]).astimezone(TZ)

        events.append(Event(
            name=name,
            start_time=start,
            end_time=None,
            location=e.get("venue_name"),
            description=e.get("description"),
            source_url=url,
            source=SOURCE,
            unique_key=Event.build_unique_key(name, start),
        ))

    return events