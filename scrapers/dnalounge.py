def _parse_page(html: str) -> List[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: List[Event] = []

    for box in soup.select(".blurbox"):
        text = box.get_text(" ", strip=True)

        if not text:
            continue

        name = text.split(" - ")[0]

        events.append(Event(
            name=name,
            start_time=datetime.now(TZ),
            end_time=None,
            location="DNA Lounge",
            description=text,
            source_url="https://www.dnalounge.com/",
            source=SOURCE,
            unique_key=Event.build_unique_key(name, datetime.now(TZ)),
        ))

    return events