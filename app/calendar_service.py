from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.event_model import Event
from config.settings import CLIENT_SECRETS_FILE, DEFAULT_TIMEZONE, SCOPES, TOKEN_FILE

logger = logging.getLogger(__name__)

_KEY_FIELD = "unique_key"
_HASH_FIELD = "content_hash"
_SOURCE_FIELD = "source"


def get_credentials() -> Credentials:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    creds: Optional[Credentials] = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def build_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds)


def get_or_create_calendar(service, name: str) -> str:
    """Return the calendar ID for the named calendar, creating it if absent."""
    page_token = None
    while True:
        resp = service.calendarList().list(pageToken=page_token).execute()
        for cal in resp.get("items", []):
            if cal.get("summary") == name:
                logger.info(f"Found calendar '{name}' ({cal['id']})")
                return cal["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    new_cal = service.calendars().insert(body={"summary": name}).execute()
    logger.info(f"Created calendar '{name}' ({new_cal['id']})")
    return new_cal["id"]


def fetch_existing_events(service, calendar_id: str) -> dict[str, dict]:
    """Return {unique_key: {event_id, content_hash}} for all upcoming events."""
    result: dict[str, dict] = {}
    time_min = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
    page_token = None

    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            singleEvents=True,
            maxResults=2500,
            timeMin=time_min,
            pageToken=page_token,
        ).execute()

        for item in resp.get("items", []):
            private = item.get("extendedProperties", {}).get("private", {})
            key = private.get(_KEY_FIELD)
            if key:
                result[key] = {
                    "event_id": item["id"],
                    "content_hash": private.get(_HASH_FIELD, ""),
                }

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return result


def _gcal_datetime(dt: datetime) -> dict:
    if dt.tzinfo is None:
        dt = pytz.timezone(DEFAULT_TIMEZONE).localize(dt)
    iana_name = getattr(dt.tzinfo, "zone", None) or DEFAULT_TIMEZONE
    return {"dateTime": dt.isoformat(), "timeZone": iana_name}


def _build_body(event: Event) -> dict:
    end = event.end_time or (event.start_time + timedelta(hours=1))
    description = (event.description or "") + f"\n\nSource: {event.source_url}"
    return {
        "summary": event.name,
        "description": description.strip(),
        "location": event.location,
        "start": _gcal_datetime(event.start_time),
        "end": _gcal_datetime(end),
        "extendedProperties": {
            "private": {
                _KEY_FIELD: event.unique_key,
                _HASH_FIELD: event.content_hash(),
                _SOURCE_FIELD: event.source,
            }
        },
    }


def insert_event(service, calendar_id: str, event: Event) -> None:
    service.events().insert(calendarId=calendar_id, body=_build_body(event)).execute()
    logger.debug(f"Inserted '{event.name}'")


def update_event(service, calendar_id: str, event_id: str, event: Event) -> None:
    service.events().update(
        calendarId=calendar_id, eventId=event_id, body=_build_body(event)
    ).execute()
    logger.debug(f"Updated '{event.name}'")
