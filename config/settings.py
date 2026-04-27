from __future__ import annotations

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENT_SECRETS_FILE = os.path.join(_BASE, "client_secret.json")
TOKEN_FILE = os.path.join(_BASE, "token.json")
PUSH_HISTORY_FILE = os.path.join(_BASE, "push_history.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"

SOURCES: dict[str, dict] = {
    "luma": {
        "label": "Luma",
        "emoji": "💡",
        "display_url": "https://luma.com/sf",
        "calendar": "SF Luma",
    },
    "partiful": {
        "label": "Partiful",
        "emoji": "🥳",
        "display_url": "https://partiful.com/explore/sf",
        "calendar": "SF Partiful",
    },
    "funcheap": {
        "label": "SF Funcheap",
        "emoji": "😜",
        "display_url": "https://sf.funcheap.com/region/san-francisco/",
        "calendar": "SF Fun Cheap",
    },
    "the_faight": {
        "label": "The Faight",
        "emoji": "🔮",
        "display_url": "https://www.thefaight.com/events",
        "calendar": "SF Arts/Culture",
    },
    "tiat": {
        "label": "TIAT Art and Tech",
        "emoji": "🤖",
        "display_url": "https://luma.com/tiat",
        "calendar": "SF Arts/Culture",
    },
    "decentered_featured_events": {
        "label": "Decentered Featured Events",
        "emoji": "😵‍💫",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Arts/Culture",
    },    
    "dnalounge": {
        "label": "DNA Lounge",
        "emoji": "🧬",
        "display_url": "https://www.dnalounge.com/calendar/latest.html",
        "calendar": "SF Nightclubs",
    },
    "makeout_room": {
        "label": "Make-Out Room",
        "emoji": "💋",
        "display_url": "http://www.makeoutroom.com/",
        "calendar": "SF Bars",
    },
    "great_american_music_hall": {
        "label": "Great American Music Hall",
        "emoji": "🇺🇸",
        "display_url": "https://gamh.com/calendar/",
        "calendar": "SF Music",
    },
    "roxie_theater": {
        "label": "Roxie Theater",
        "emoji": "🪨",
        "display_url": "https://roxie.com/calendar/",
        "calendar": "SF Movies",
    },
    "decentered_community_events": {
        "label": "Decentered Community Events",
        "emoji": "👥",
        "display_url": "https://decentered.org/events",
        "calendar": "SF Other",
    },
    "mannys": {
        "label": "Manny's: Community, Politics, and Culture",
        "emoji": "👨‍🦰",
        "display_url": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
        "calendar": "SF Other",
    },
    "pebblebed": {
        "label": "Pebblebed Tech Events on Luma",
        "emoji": "🪨",
        "display_url": "https://luma.com/pebblebedevents",
        "calendar": "SF Tech",
    },
}

# Maps Google Calendar name → list of scraper module names (under scrapers/)
CALENDARS: dict[str, list[str]] = {
    cal: [src for src, meta in SOURCES.items() if meta["calendar"] == cal]
    for cal in dict.fromkeys(meta["calendar"] for meta in SOURCES.values())
}

