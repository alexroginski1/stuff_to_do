def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    desc = soup.find("meta", property="og:description")
    if not desc:
        return []

    text = desc.get("content", "")
    if not text:
        return []

    name = text.split("~")[0].strip()

    events.append(Event(
        name=name,
        start_time=datetime.now(TZ),
        end_time=None,
        location="Make-Out Room",
        description=text,
        source_url="http://www.makeoutroom.com/",
        source=SOURCE,
        unique_key=Event.build_unique_key(name, datetime.now(TZ)),
    ))

    return events