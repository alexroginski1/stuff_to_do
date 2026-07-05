from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import partial

import google.auth
import pytz
from google.auth.credentials import Credentials
from googleapiclient.discovery import build

from app.event_model import Event
from app.utils import fetch_eventbrite_price, format_readable_dt
from config.settings import DEFAULT_TIMEZONE, SCOPES, SOURCES

logger = logging.getLogger(__name__)

_KEY_FIELD = "unique_key"
_SOURCE_FIELD = "source"


def get_credentials() -> Credentials:
    """Application Default Credentials — the Cloud Run job's attached service account.

    Requires the target calendar(s) to be shared with that service account's
    email, granting "Make changes to events". No token file, no refresh, no expiry.
    """
    creds, _ = google.auth.default(scopes=SCOPES)
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


def fetch_existing_events(service, calendar_id: str, source: str) -> dict[str, str]:
    """Return {unique_key: event_id} for all upcoming parser-created events from `source`."""
    result: dict[str, str] = {}
    time_min = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
    page_token = None
    props = [f"{_SOURCE_FIELD}={source}"]

    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=props,
            singleEvents=True,
            maxResults=2500,
            timeMin=time_min,
            pageToken=page_token,
        ).execute()

        for item in resp.get("items", []):
            private = item.get("extendedProperties", {}).get("private", {})
            key = private.get(_KEY_FIELD)
            if key:
                result[key] = item["id"]

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
    source: str | None = None,
) -> list[str]:
    """Delete parser-created events from today onwards. Optionally filter by source.

    Returns the unique_keys of deleted events.
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


_BATCH_SIZE = 50


def delete_events_older_than(service, calendar_id: str, days: int = 7) -> int:
    """Delete events on the calendar that started more than `days` days ago. Returns count deleted.

    Deletes are sent via the API's HTTP batch endpoint (up to _BATCH_SIZE per
    request) instead of one call per event, since Calendar has no native
    delete-by-query/range operation.
    """
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
        events = resp.get("items", [])
        for i in range(0, len(events), _BATCH_SIZE):
            chunk = events[i : i + _BATCH_SIZE]
            chunk_deleted = 0

            def _on_response(request_id, response, exception, event=None):
                nonlocal chunk_deleted
                if exception is not None:
                    logger.warning(f"[DELETE-OLD] failed for {_gcal_event_display(event)}: {exception}")
                else:
                    logger.info(f"[DELETE-OLD] {_gcal_event_display(event)}")
                    chunk_deleted += 1

            batch = service.new_batch_http_request()
            for event in chunk:
                batch.add(
                    service.events().delete(calendarId=calendar_id, eventId=event["id"]),
                    callback=partial(_on_response, event=event),
                )
            batch.execute()
            deleted += chunk_deleted
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return deleted


def insert_event(service, calendar_id: str, event: Event) -> None:
    service.events().insert(calendarId=calendar_id, body=_build_body(event)).execute()
    logger.info(f"[APPEND] {event.name} ({format_readable_dt(event.start_time)})")
