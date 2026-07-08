"""Delete all parser-created Google Calendar events using your local OAuth
token (tokens/token.json) instead of the Cloud Run service account.

Run from the repo root:
    python -m scripts.delete_parser_events_local
    python -m scripts.delete_parser_events_local --calendar "SF Bars"
    python -m scripts.delete_parser_events_local --source luma_tiat
"""

from __future__ import annotations

import argparse
import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.calendar_service import build_service, delete_all_parser_events
from app.utils import setup_logging
from config.settings import CALENDAR_IDS, SCOPES

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOKEN_PATH = os.path.join(_BASE, "tokens", "token.json")
_CLIENT_SECRETS_PATH = os.path.join(_BASE, "tokens", "client_secret.json")


def _get_local_credentials() -> Credentials:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    creds: Credentials | None = None

    if os.path.exists(_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.warning(f"Token refresh failed ({e}), re-authenticating...")
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(_CLIENT_SECRETS_PATH, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete parser-created events using the local OAuth token")
    parser.add_argument("--source", type=str, default=None, help="Limit deletion to a specific source")
    parser.add_argument("--calendar", type=str, default=None, help="Limit deletion to one calendar name (default: all)")
    args = parser.parse_args()

    setup_logging()
    creds = _get_local_credentials()
    service = build_service(creds)

    calendars = {args.calendar: CALENDAR_IDS[args.calendar]} if args.calendar else CALENDAR_IDS
    for name, calendar_id in calendars.items():
        deleted_keys = delete_all_parser_events(service, calendar_id, source=args.source)
        logging.info(f"[{name}] deleted parser events={len(deleted_keys)}")


if __name__ == "__main__":
    main()
