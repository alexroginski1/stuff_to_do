from __future__ import annotations

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENT_SECRETS_FILE = os.path.join(_BASE, "client_secret.json")
TOKEN_FILE = os.path.join(_BASE, "token.json")
PUSH_HISTORY_FILE = os.path.join(_BASE, "push_history.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"

# Emoji prefix for each scraper module
SOURCE_EMOJIS: dict[str, str] = {
    "partiful": "🥳",
    "luma": "💡",
    "funcheap": "😜",
    "makeout_room": "💋",
    "dnalounge": "🧬",
    "decentered": "😵‍💫",
    "the_faight": "🔮",
    "luma_tiat": "🤖",
    "great_american_music_hall": "🇺🇸",
    "roxie_theater": "🪨",
    "mannys": "👨‍🦰",
}

# Friendly display URLs for the event source page (keyed by each scraper's SOURCE constant).
# Used as the hyperlink target for the source name in calendar event descriptions.
SOURCE_DISPLAY_URLS: dict[str, str] = {
    "luma": "https://luma.com/sf",
    "tiat": "https://luma.com/tiat",
    "luma_tiat": "https://luma.com/tiat",
    "partiful": "https://partiful.com/explore/sf",
    "funcheap": "https://sf.funcheap.com/region/san-francisco/",
    "the_faight": "https://www.thefaight.com/events",
    "decentered": "https://decentered.org/events",
    "dnalounge": "https://www.dnalounge.com/calendar/latest.html",
    "makeoutroom": "http://www.makeoutroom.com/",
    "gamh": "https://gamh.com/calendar/",
    "roxie": "https://roxie.com/calendar/",
    "Manny's | Eventbrite": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
    "mannys": "https://www.eventbrite.com/o/mannys-community-politics-and-culture-15114280512",
}

# Human-readable display names for each scraper module
SCRAPER_LABELS: dict[str, str] = {
    "luma": "Luma",
    "tiat": "TIAT Art and Tech",
    "partiful": "Partiful",
    "funcheap": "SF Funcheap",
    "great_american_music_hall": "Great American Music Hall",
    "the_faight": "The Faight",
    "decentered": "Decentered Arts",
    "dnalounge": "DNA Lounge",
    "makeout_room": "Make-Out Room",
    "roxie_theater": "Roxie Theater",
    "luma_tiat": "TIAT: intersection of art and tech",
    "mannys": "Manny's: Community, Politics, and Culture"
}

# Maps Google Calendar name → list of scraper module names (under scrapers/)
CALENDARS: dict[str, list[str]] = {
    # "SF Partiful": ["partiful"],
    # "SF Luma": ["luma"],
    # "SF Fun Cheap": ["funcheap"],
    # "SF Bars": ["makeout_room"],
    # "SF Nightclubs": ["dnalounge"],
    "SF Arts/Culture": ["decentered","the_faight","luma_tiat"],
    # "SF Music": ["great_american_music_hall"],
    # "SF Movies": ["roxie_theater"],
    # "SF Other": ["mannys"]
}

