from __future__ import annotations

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENT_SECRETS_FILE = os.path.join(_BASE, "client_secret.json")
TOKEN_FILE = os.path.join(_BASE, "token.json")
PUSH_HISTORY_FILE = os.path.join(_BASE, "push_history.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"

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
}

# Maps Google Calendar name → list of scraper module names (under scrapers/)
CALENDARS: dict[str, list[str]] = {
    # "SF Partiful": ["partiful"],
    # "SF Luma": ["luma"],
    # "SF Fun Cheap": ["funcheap"],
    # "SF Bars": ["makeout_room"],
    # "SF Nightclubs": ["dnalounge"],
    # "SF Arts/Culture": ["decentered","the_faight","luma_tiat"],
    # "SF Music": ["great_american_music_hall"],
    # "SF Movies": ["roxie_theater"],
    "Other": ["mannys"]
}

