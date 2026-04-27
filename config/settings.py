from __future__ import annotations

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENT_SECRETS_FILE = os.path.join(_BASE, "client_secret.json")
TOKEN_FILE = os.path.join(_BASE, "token.json")
PUSH_HISTORY_FILE = os.path.join(_BASE, "push_history.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"

SOURCES: dict[str, dict] = {
    "the_faight": {
        "label": "The Faight",
        "emoji": "🔮",
        "display_url": "https://www.thefaight.com/events",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "luma_tiat": {
        "label": "TIAT Art and Tech",
        "emoji": "🤖",
        "display_url": "https://luma.com/tiat",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "decentered_featured_events": {
        "label": "Decentered Featured Events",
        "emoji": "😵‍💫",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Arts/Culture",
        "enabled": True,
    },
    "makeout_room": {
        "label": "Make-Out Room",
        "emoji": "💋",
        "display_url": "http://www.makeoutroom.com/",
        "calendar": "SF Bars",
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
    "roxie_theater": {
        "label": "Roxie Theater",
        "emoji": "🪨",
        "display_url": "https://roxie.com/calendar/",
        "calendar": "SF Movies",
        "enabled": True,
    },
    "great_american_music_hall": {
        "label": "Great American Music Hall",
        "emoji": "🇺🇸",
        "display_url": "https://gamh.com/calendar/",
        "calendar": "SF Music",
        "enabled": True,
    },
    "dnalounge": {
        "label": "DNA Lounge",
        "emoji": "🧬",
        "display_url": "https://www.dnalounge.com/calendar/latest.html",
        "calendar": "SF Nightclubs",
        "enabled": True,
    },
    "decentered_community_events": {
        "label": "Decentered Community Events",
        "emoji": "👥",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Other",
        "enabled": True,
    },
    "mannys": {
        "label": "Manny's: Community, Politics, and Culture",
        "emoji": "👨‍🦰",
        "display_url": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
        "calendar": "SF Other",
        "enabled": True,
    },
    "the_sf_nook": {
        "label": "The SF Nook: SF Event Space",
        "emoji": "🏠",
        "display_url": "https://www.thesfnook.com/events",
        "calendar": "SF Other",
        "enabled": True,
    },
    "partiful": {
        "label": "Partiful",
        "emoji": "🥳",
        "display_url": "https://partiful.com/explore/sf",
        "calendar": "SF Partiful",
        "enabled": True,
    },
    "luma_pebblebed": {
        "label": "Pebblebed Tech Events on Luma",
        "emoji": "🪨",
        "display_url": "https://luma.com/pebblebedevents",
        "calendar": "SF Tech",
        "enabled": True,
    },
}

# Maps Google Calendar name → list of scraper module names (under scrapers/)
CALENDARS: dict[str, list[str]] = {
    cal: [src for src, meta in SOURCES.items() if meta["calendar"] == cal and meta.get("enabled", True)]
    for cal in dict.fromkeys(meta["calendar"] for meta in SOURCES.values() if meta.get("enabled", True))
}

