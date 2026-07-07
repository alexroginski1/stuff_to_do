from __future__ import annotations

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"


# Google Calendar IDs (Settings > Integrate calendar > Calendar ID), keyed by
# display name. This is what the service account needs to address the
# calendar via the Calendar API.
CALENDAR_LINKS = {
    "SF Arts/Culture": "7f66e10ca74622780fdf0db852f0dc8e4be2272cf206bfc8cf83f2eaefc8abdf@group.calendar.google.com",
    "SF Community": "c40ce35591588f6a8cf1d14e96f4ec215f2d812857382a0fb7253eabea1a0154@group.calendar.google.com",
    "SF Fun Cheap": "60a19fdad14c75dc604082f022416e48c2d30dc440502a5e80bf410d32570d1d@group.calendar.google.com",
    "SF Partiful": "9d7c77c609ffc954909e2a0cb72e2c2b5029048fe87d0ba6a035ccac18e1472a@group.calendar.google.com",
    "SF Tech": "45264416fab34dddf5fff1ca40931d59a13f865ec441d158030be512b30d6b15@group.calendar.google.com",
    "SF Bars": "9c8685a68b697409a5bffa6ce3011651930fa18572dad9ef435215753a43de22@group.calendar.google.com",
    "SF Dancing": "704367c0fe7ec0383a79ab3bd6a4388d8c867642120862ffa11191fdb27e407f@group.calendar.google.com",
}


# Maps display name → actual Google Calendar ID. This is what gets passed to
# the Calendar API — never a calendar name.
CALENDAR_IDS: dict[str, str] = dict(CALENDAR_LINKS)


# Per-calendar duplicate-detection rules, checked across every source feeding
# that calendar (not just within one scraper) so e.g. two different arts
# calendars covering the same gallery opening get caught. Two events are
# duplicates if they match on every field in "fields" and their start times
# are within "time_window_minutes" of each other. Matching is chained: if A
# and B are within the window and B and C are within the window, A/B/C are
# all treated as one duplicate group even if A and C alone are not.
# Calendars not listed here fall back to DEFAULT_DEDUP_RULE (exact title +
# exact start time, i.e. the original behavior).
DEFAULT_DEDUP_RULE: dict = {"fields": ("summary",), "time_window_minutes": 0}

DEDUP_RULES: dict[str, dict] = {
    # Art gallery openings get posted with different titles/wording by
    # different sources (e.g. ArtBae vs. ArtBusiness), but a real duplicate
    # is always the same gallery at the same time, so match on location only.
    "SF Arts/Culture": {"fields": ("location",), "time_window_minutes": 30},
}




SOURCES: dict[str, dict] = {
    "the_faight": {
        "label": "The Faight",
        "location": "Lower Haight",
        "location_link": "https://maps.app.goo.gl/sD1asWWUYL11KqmEA",
        "emoji": "🔮",
        "display_url": "https://www.thefaight.com/events",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "decentered_featured_events": {
        "label": "Decentered Featured Events",
        "location": "SOMA 8th St",
        "location_link": "https://maps.app.goo.gl/vzyNdBP39hJtJ2XC9",
        "emoji": "😵‍💫",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "funcheap": {
        "label": "SF Funcheap",
        "emoji": "😜",
        "display_url": "https://sf.funcheap.com/region/san-francisco/",
        "calendar": "SF Fun Cheap",
        "enabled": True,
    },
    "luma": {
        "label": "Luma",
        "emoji": "💡",
        "display_url": "https://luma.com/sf",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "decentered_community_events": {
        "label": "Decentered Community Events",
        "location": "SOMA 8th St",
        "location_link": "https://maps.app.goo.gl/vzyNdBP39hJtJ2XC9",
        "emoji": "👥",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Community",
        "enabled": True,
    },
    "mannys": {
        "label": "Manny's: Community, Politics, and Culture",
        "location": "Mission 16th St",
        "location_link": "https://maps.app.goo.gl/wyEqhBaKK8M7sU1Q9",
        "emoji": "👨‍🦰",
        "display_url": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
        "calendar": "SF Community",
        "enabled": True,
    },
    "the_sf_nook": {
        "label": "The SF Nook: SF Event Space",
        "location": "Civic Center on Market St",
        "location_link": "https://maps.app.goo.gl/MbiV4DbkXNUp12QLA",
        "emoji": "🏠",
        "display_url": "https://www.thesfnook.com/events",
        "calendar": "SF Community",
        "enabled": True,
    },
    "luma_the_commons": {
        "label": "The Commons: Third Space",
        "location": "Hayes Valley",
        "location_link": "https://maps.app.goo.gl/URPfH9ePaBTm3YRd9",
        "emoji": "🏛️",
        "display_url": "https://luma.com/thecommons",
        "calendar": "SF Community",
        "enabled": True,
    },
    "luma_future_of_us": {
        "label": "Future of Us",
        "emoji": "⚡",
        "display_url": "https://luma.com/future-of-us",
        "calendar": "SF Community",
        "enabled": True,
    },
    "the_sf_contemplarium": {
        "label": "The SF Contemplarium",
        "emoji": "📓",
        "display_url": "https://luma.com/sfcontemplarium",
        "calendar": "SF Community",
        "enabled": True,
    },
    "luma_tiat": {
        "label": "TIAT Art and Tech",
        "location": "Downtown: Powell and O'Farrell",
        "location_link": "https://maps.app.goo.gl/phgTf8BvmnwwKht87",
        "emoji": "🤖",
        "display_url": "https://luma.com/tiat",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "partiful": {
        "label": "Partiful",
        "emoji": "🥳",
        "display_url": "https://partiful.com/explore/sf",
        "calendar": "SF Partiful",
        "enabled": True,
    },
    "mox": {
        "label": "Mox Event Space",
        "location": "Mission 13th St",
        "location_link": "https://maps.app.goo.gl/1rUtdL99NgpzCrcbA",
        "emoji": "💻",
        "display_url": "https://moxsf.com/events",
        "calendar": "SF Tech",
        "enabled": True,
    },
    "artbae": {
        "label": "Art Bae",
        "emoji": "🎨",
        "display_url": "https://www.artbae.info/map-calendar",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "artbusiness": {
        "label": "SF Art Galleries - Openings & Events",
        "emoji": "🖼️",
        "display_url": "https://calendar.google.com/calendar/embed?src=33alanb%40gmail.com&ctz=America%2FLos_Angeles",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "madrone_art_bar": {
        "label": "Madrone Art Bar",
        "location": "Alamo Square",
        "location_link": "https://maps.app.goo.gl/drHLFmYXNrUshseR6",
        "emoji": "🎨",
        "display_url": "https://www.eventbrite.com/o/madrone-art-bar-33448786911",
        "calendar": "SF Bars",
        "enabled": True,
    },
    "moonlit_moves": {
        "label": "Moonlit Moves: Mission 22nd St",
        "location": "The Polish Club Inc., 3040 22nd St",
        "location_link": "https://www.google.com/maps/search/?api=1&query=The+Polish+Club+Inc.%2C+3040+22nd+St%2C+San+Francisco%2C+CA+94110",
        "emoji": "🌙",
        "display_url": "https://calendar.google.com/calendar/embed?src=f3bfcf5b10ff8cb2ba35abba749ccd68bc8347e2d522e6baca32448c9b2695cc%40group.calendar.google.com&ctz=America%2FLos_Angeles",
        "calendar": "SF Dancing",
        "enabled": True,
    },
}

# Maps Google Calendar display name → list of scraper module names (under scrapers/).
# Use CALENDAR_IDS[name] to get the actual calendar ID to push events to.
CALENDARS: dict[str, list[str]] = {
    cal: [src for src, meta in SOURCES.items() if meta["calendar"] == cal and meta.get("enabled", True)]
    for cal in dict.fromkeys(meta["calendar"] for meta in SOURCES.values() if meta.get("enabled", True))
}

