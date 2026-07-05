from __future__ import annotations

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"

SOURCES: dict[str, dict] = {

    "the_faight": {
        "label": "The Faight",
        "location": "Lower Haight",
        "location_link": "https://maps.app.goo.gl/sD1asWWUYL11KqmEA",
        "emoji": "🔮",
        "display_url": "https://www.thefaight.com/events",
        "calendar": "SF TESTING",
        "enabled": True,
    },

    # "the_faight": {
    #     "label": "The Faight",
    #     "location": "Lower Haight",
    #     "location_link": "https://maps.app.goo.gl/sD1asWWUYL11KqmEA",
    #     "emoji": "🔮",
    #     "display_url": "https://www.thefaight.com/events",
    #     "calendar": "SF Arts/Culture",
    #     "enabled": False,
    # },
    "decentered_featured_events": {
        "label": "Decentered Featured Events",
        "location": "SOMA 8th St",
        "location_link": "https://maps.app.goo.gl/vzyNdBP39hJtJ2XC9",
        "emoji": "😵‍💫",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Arts/Culture",
        "enabled": False,
    },
    "funcheap": {
        "label": "SF Funcheap",
        "emoji": "😜",
        "display_url": "https://sf.funcheap.com/region/san-francisco/",
        "calendar": "SF Fun Cheap",
        "enabled": False,
    },
    "luma": {
        "label": "Luma",
        "emoji": "💡",
        "display_url": "https://luma.com/sf",
        "calendar": "SF Luma",
        "enabled": False,
    },
    "decentered_community_events": {
        "label": "Decentered Community Events",
        "location": "SOMA 8th St",
        "location_link": "https://maps.app.goo.gl/vzyNdBP39hJtJ2XC9",
        "emoji": "👥",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Community",
        "enabled": False,
    },
    "mannys": {
        "label": "Manny's: Community, Politics, and Culture",
        "location": "Mission 16th St",
        "location_link": "https://maps.app.goo.gl/wyEqhBaKK8M7sU1Q9",
        "emoji": "👨‍🦰",
        "display_url": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
        "calendar": "SF Community",
        "enabled": False,
    },
    "the_sf_nook": {
        "label": "The SF Nook: SF Event Space",
        "location": "Civic Center on Market St",
        "location_link": "https://maps.app.goo.gl/MbiV4DbkXNUp12QLA",
        "emoji": "🏠",
        "display_url": "https://www.thesfnook.com/events",
        "calendar": "SF Community",
        "enabled": False,
    },
    "luma_the_commons": {
        "label": "The Commons: Third Space",
        "location": "Hayes Valley",
        "location_link": "https://maps.app.goo.gl/URPfH9ePaBTm3YRd9",
        "emoji": "🏛️",
        "display_url": "https://luma.com/thecommons",
        "calendar": "SF Community",
        "enabled": False,
    },
    "luma_tiat": {
        "label": "TIAT Art and Tech",
        "location": "Downtown: Powell and O'Farrell",
        "location_link": "https://maps.app.goo.gl/phgTf8BvmnwwKht87",
        "emoji": "🤖",
        "display_url": "https://luma.com/tiat",
        "calendar": "SF Arts/Culture",
        "enabled": False,
    },
    "partiful": {
        "label": "Partiful",
        "emoji": "🥳",
        "display_url": "https://partiful.com/explore/sf",
        "calendar": "SF Partiful",
        "enabled": False,
    }
}

# Maps Google Calendar name → list of scraper module names (under scrapers/)
CALENDARS: dict[str, list[str]] = {
    cal: [src for src, meta in SOURCES.items() if meta["calendar"] == cal and meta.get("enabled", True)]
    for cal in dict.fromkeys(meta["calendar"] for meta in SOURCES.values() if meta.get("enabled", True))
}

