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
    "SF Luma": "45264416fab34dddf5fff1ca40931d59a13f865ec441d158030be512b30d6b15@group.calendar.google.com",
}


# Maps display name → actual Google Calendar ID. This is what gets passed to
# the Calendar API — never a calendar name.
CALENDAR_IDS: dict[str, str] = dict(CALENDAR_LINKS)




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
        "calendar": "SF Luma",
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
    }
}

# Maps Google Calendar display name → list of scraper module names (under scrapers/).
# Use CALENDAR_IDS[name] to get the actual calendar ID to push events to.
CALENDARS: dict[str, list[str]] = {
    cal: [src for src, meta in SOURCES.items() if meta["calendar"] == cal and meta.get("enabled", True)]
    for cal in dict.fromkeys(meta["calendar"] for meta in SOURCES.values() if meta.get("enabled", True))
}

