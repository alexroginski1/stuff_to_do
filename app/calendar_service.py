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

import app.push_history as push_history
from app.event_model import Event
from app.utils import fetch_eventbrite_price, format_readable_dt
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
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token refresh failed ({e}), re-authenticating...")
                os.remove(TOKEN_FILE)
                creds = None
        if not creds or not creds.valid:
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

    # Fetch price for Eventbrite events
    eventbrite_price: str | None = None
    if event.source_url and "eventbrite.com" in event.source_url:
        eventbrite_price = fetch_eventbrite_price(event.source_url)

    location = src_meta.get("location")
    location_link = src_meta.get("location_link")
    if location and location_link:
        location_str = f' (<a href="{location_link}">{location}</a>)'
    elif location:
        location_str = f" ({location})"
    else:
        location_str = ""
    parts = [f'<a href="{source_display_url}">{label}</a>{location_str}']

    if event.source_url and event.source_url != source_display_url:
        parts.append(f'<a href="{event.source_url}">Event Link</a>')
    else:
        parts.append("Event Link: see venue calendar above ^^")

    if eventbrite_price:
        parts.append(f"<b>Price: {eventbrite_price}</b>")

    if event.description:
        prices = _price_lines(event.description)
        if prices:
            parts.append("")
            parts.extend(prices)
        parts.append("")
        parts.append(event.description)

    description = "\n".join(parts) + _FOOTER
    emoji = src_meta.get("emoji", "")
    name_with_price = f"{event.name} ({eventbrite_price})" if eventbrite_price else event.name
    summary = f"{emoji} {name_with_price}" if emoji else name_with_price
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
                "created_by": "event_parser",
                "parser_version": "v1",
            }
        },
    }


def _gcal_event_display(event: dict) -> str:
    """Return 'Name (readable datetime)' for a raw Google Calendar event resource."""
    name = event.get("summary", "(no title)")
    raw = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
    if raw:
        try:
            when = format_readable_dt(datetime.fromisoformat(raw))
        except ValueError:
            when = raw
    else:
        when = "unknown time"
    return f"{name} ({when})"


def delete_event(service, calendar_id: str, event_id: str) -> None:
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    logger.info(f"[DELETE] {_gcal_event_display(event)}")


def delete_all_parser_events(
    service,
    calendar_id: str,
    calendar_name: str,
    history: push_history.History,
    source: str | None = None,
) -> list[str]:
    """Delete parser-created events from today onwards. Optionally filter by source.

    Removes each deleted event's key from `history` (caller is responsible for
    persisting it via push_history.save). Returns unique_keys of deleted events.
    """
    deleted_keys: list[str] = []
    page_token = None
    time_min = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    props = ["created_by=event_parser"]
    if source:
        props.append(f"{_SOURCE_FIELD}={source}")
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=props,
            singleEvents=True,
            timeMin=time_min,
            maxResults=2500,
            pageToken=page_token,
        ).execute()
        for event in resp.get("items", []):
            service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
            logger.info(f"[DELETE] {_gcal_event_display(event)}")
            key = event.get("extendedProperties", {}).get("private", {}).get(_KEY_FIELD)
            if key:
                deleted_keys.append(key)
                push_history.remove(history, calendar_name, key)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return deleted_keys


def delete_all_events(service, calendar_id: str, source: str | None = None) -> int:
    """Delete all events (including manual) from today onwards. Optionally filter by source. Returns count deleted."""
    deleted = 0
    page_token = None
    time_min = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    list_kwargs: dict = dict(
        calendarId=calendar_id,
        singleEvents=True,
        timeMin=time_min,
        maxResults=2500,
    )
    if source:
        list_kwargs["privateExtendedProperty"] = f"{_SOURCE_FIELD}={source}"
    while True:
        resp = service.events().list(pageToken=page_token, **list_kwargs).execute()
        for event in resp.get("items", []):
            service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
            logger.info(f"[DELETE] {_gcal_event_display(event)}")
            deleted += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return deleted


def delete_events_older_than(service, calendar_id: str, days: int = 7) -> int:
    """Delete events on the calendar that started more than `days` days ago. Returns count deleted."""
    deleted = 0
    page_token = None
    time_max = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            singleEvents=True,
            timeMax=time_max,
            maxResults=2500,
            pageToken=page_token,
        ).execute()
        for event in resp.get("items", []):
            service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
            logger.info(f"[DELETE-OLD] {_gcal_event_display(event)}")
            deleted += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return deleted


def insert_event(service, calendar_id: str, event: Event) -> None:
    service.events().insert(calendarId=calendar_id, body=_build_body(event)).execute()
    logger.info(f"[APPEND] {event.name} ({format_readable_dt(event.start_time)})")


def update_event(service, calendar_id: str, event_id: str, event: Event) -> None:
    service.events().update(
        calendarId=calendar_id, eventId=event_id, body=_build_body(event)
    ).execute()
    logger.info(f"[UPDATE] {event.name} ({format_readable_dt(event.start_time)})")
