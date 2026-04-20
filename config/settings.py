from __future__ import annotations

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CLIENT_SECRETS_FILE = os.path.join(_BASE, "client_secret.json")
TOKEN_FILE = os.path.join(_BASE, "token.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_TIMEZONE = "America/Los_Angeles"

# Maps Google Calendar name → list of scraper module names (under scrapers/)
CALENDARS: dict[str, list[str]] = {
    "Main Aggregated Calendar": ["partiful", "luma", "funcheap", "brokeassstuart"],
    "Bars/Clubs": ["makeoutroom", "dnalounge"],
    "Arts/Culture": ["decentered", "the_faight"],
    "Music": ["regency_ballroom", "great_american_music_hall", "sf_jazz"],
}
