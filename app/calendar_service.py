from __future__ import annotations

import json
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
from config.settings import CLIENT_SECRETS_FILE, DEFAULT_TIMEZONE, SCOPES, SOURCES, TOKEN_FILE

logger = logging.getLogger(__name__)

_KEY_FIELD = "unique_key"
_HASH_FIELD = "content_hash"
_SOURCE_FIELD = "source"

_CLOUD_CLIENT_SECRET_NAME = "calendar-client-secret"
_CLOUD_TOKEN_SECRET_NAME = "calendar-token"


def get_credentials() -> Credentials:
    from app.gcp import is_cloud

    if is_cloud():
        return _get_cloud_credentials()
    return _get_local_credentials()


def _get_local_credentials() -> Credentials:
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


def _get_cloud_credentials() -> Credentials:
    from app.gcp import read_secret, write_secret

    token_json = read_secret(_CLOUD_TOKEN_SECRET_NAME)
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            write_secret(_CLOUD_TOKEN_SECRET_NAME, creds.to_json())
            logger.info("Cloud token refreshed and saved to Secret Manager")
        else:
            raise RuntimeError(
                "Cloud credentials are invalid and cannot be refreshed non-interactively. "
                "Run locally to obtain a fresh token.json, then re-upload it to Secret Manager."
            )

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


_FOOTER = (
    "\n――――――――――\n"
    '<a href="https://docs.google.com/spreadsheets/d/1x1EeFDPKNDULmW1_EE-4xsTcPV0RQ7pdZd4oK_fh0Dg/edit?gid=545113219#gid=545113219">SF Stuff To Do</a>'
)


def _price_lines(description: str) -> list[str]:
    return [line for line in description.splitlines() if "$" in line]


def _build_body(event: Event) -> dict:
    end = event.end_time or (event.start_time + timedelta(hours=1))
    src_meta = SOURCES.get(event.source, {})
    label = src_meta.get("label", event.source)
    source_display_url = src_meta.get("display_url", event.source_url)

    parts = [f'<a href="{source_display_url}">{label}</a>']

    if event.source_url and event.source_url != source_display_url:
        parts.append(f'<a href="{event.source_url}">Event Link</a>')
    else:
        parts.append("No event link provided")

    if event.description:
        prices = _price_lines(event.description)
        if prices:
            parts.append("")
            parts.extend(prices)
        parts.append("")
        parts.append(event.description)

    description = "\n".join(parts) + _FOOTER
    emoji = src_meta.get("emoji", "")
    summary = f"{emoji} {event.name}" if emoji else event.name
    return {
        "summary": summary,
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


def delete_event(service, calendar_id: str, event_id: str) -> None:
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    logger.debug(f"Deleted event {event_id}")


def insert_event(service, calendar_id: str, event: Event) -> None:
    service.events().insert(calendarId=calendar_id, body=_build_body(event)).execute()
    logger.debug(f"Inserted '{event.name}'")


def update_event(service, calendar_id: str, event_id: str, event: Event) -> None:
    service.events().update(
        calendarId=calendar_id, eventId=event_id, body=_build_body(event)
    ).execute()
    logger.debug(f"Updated '{event.name}'")
