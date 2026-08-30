from __future__ import annotations

import importlib
import logging
import re
import time
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from app.calendar_service import (
    build_service,
    delete_all_parser_events,
    delete_duplicate_events,
    delete_event,
    delete_events_older_than,
    event_time_matches,
    fetch_all_events,
    fetch_existing_events,
    get_credentials,
    insert_event,
)

from app.event_model import Event
from app.event_snapshot_store import write_snapshot
from app.location_service import resolve_location, resolve_neighborhood
from app.notifier import format_parsing_issues_email, send_error_email
from app.stats_store import record_stats
from app.utils import emit_metric
from config.settings import CALENDARS, CALENDAR_IDS, DEDUP_RULES, DEFAULT_DEDUP_RULE

logger = logging.getLogger(__name__)

_API_DELAY = 0.1  # seconds between Google Calendar write calls
_TZ = ZoneInfo("America/Los_Angeles")
_LOOKAHEAD_DAYS = 7  # how far ahead events get pushed to Google Calendar
_SNAPSHOT_LOOKAHEAD_DAYS = 7  # how far ahead the public "/" events table looks


def _parse_gcal_datetime(raw: dict) -> datetime | None:
    value = raw.get("dateTime") or raw.get("date")
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ)
    return dt
# 


def _snapshot_record(calendar_name: str, event: dict) -> dict | None:
    """Build an event_snapshot_store record from a raw Calendar API event resource.

    `created_by=event_parser` is the same private extendedProperty the sync
    engine stamps on every event it inserts (see calendar_service._build_body),
    so its absence means the event was added directly on the calendar.
    """
    start_time = _parse_gcal_datetime(event.get("start", {}))
    if start_time is None:
        return None
    end_time = _parse_gcal_datetime(event.get("end", {})) or (start_time + timedelta(hours=1))
    private_props = event.get("extendedProperties", {}).get("private", {})
    is_automatic = private_props.get("created_by") == "event_parser"
    # For parser-created events, the calendar's "location" field holds the
    # Places-resolved address (see calendar_service._build_body), not the
    # original scraped string, so the true raw location has to come from the
    # private extendedProperty stashed alongside it instead. Events pushed
    # before that property existed (pre 4f73710) never get re-inserted just
    # to pick it up — their unique_key (title+start+description+location)
    # hasn't changed, so the sync engine's key-based diff always finds them
    # unchanged and skips them. For those, the calendar's "location" field
    # *is* the raw string, since the old insert path wrote it there directly
    # without any Places resolution.
    if is_automatic:
        raw_location = private_props.get("raw_location")
        if raw_location is None:
            raw_location = event.get("location") or ""
    else:
        raw_location = event.get("location") or ""
    if private_props.get("location_verified") == "true":
        # Scraper already hardcoded a known-correct full address for this
        # event (see Event.location_verified) — no need to spend a Places
        # API call/cache entry re-resolving it. No coords, so no
        # neighborhood either — that would mean geocoding it after all.
        cleaned_location, location_type, coords = raw_location, "exact", None
    elif private_props.get("location_inexact") == "true":
        # Scraper deliberately marked this location as approximate (see
        # Event.location_inexact) — skip Places and always report inexact.
        cleaned_location, location_type, coords = raw_location, "inexact", None
    else:
        cleaned_location, location_type, coords = resolve_location(raw_location)
    neighborhood = resolve_neighborhood(cleaned_location, location_type, coords)
    return {
        "gcal_id": event["id"],
        "gcal_link": event.get("htmlLink") or "",
        "title": event.get("summary") or "(no title)",
        "description": event.get("description") or "",
        "start_time": start_time,
        "end_time": end_time,
        "raw_location": raw_location,
        "cleaned_location": cleaned_location,
        "location_type": location_type,
        "neighborhood": neighborhood,
        "calendar": calendar_name,
        "source_type": "automatic" if is_automatic else "manual",
        "source": private_props.get("source"),
    }


# Titles that mean "not actually open to the public" — never pushed to the
# calendar regardless of source. Matched case- and whitespace-insensitively
# (see `_normalize_title`), so "private event", "PRIVATE  EVENT", and
# "PrivateEvent" all match.
_BLOCKED_TITLES = {"privateevent", "membersonly"}


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", title).lower()


def _filter_events(events: List[Event], days: int = _LOOKAHEAD_DAYS) -> List[Event]:
    today = datetime.now(tz=_TZ).date()
    cutoff = today + timedelta(days=days)
    kept = []
    for e in events:
        if _normalize_title(e.name) in _BLOCKED_TITLES:
            continue
        event_date = e.start_time.astimezone(_TZ).date()
        if event_date < today:
            continue
        if event_date > cutoff:
            continue
        kept.append(e)
    return kept


def _fetch_safe(scraper_name: str, calendar_name: str, issues: List[dict]) -> List[Event]:
    try:
        module = importlib.import_module(f"scrapers.{scraper_name}")
        events = module.fetch_events()
        logger.info(f"[{scraper_name}] fetched {len(events)} events")
        return events
    except Exception as exc:
        logger.error(f"[{scraper_name}] scraper failed: {exc}", exc_info=True)
        issues.append({"calendar": calendar_name, "source": scraper_name, "message": f"Scraper failed: {exc}"})
        return []


def _sync_source(
    service, calendar_id: str, calendar_name: str, source: str, events: List[Event], issues: List[dict]
) -> dict:
    """Sync a single source's currently-live events with the calendar.

    An event's identity is its unique_key (title + start + description +
    location). Events present on the source but missing from the calendar get
    pushed; events on the calendar (tagged to this source) that are no longer
    present on the source get deleted. A changed event has a different key, so
    it naturally goes through both paths — delete the stale one, push the new
    one — rather than being updated in place.

    Even when the key matches, the event is re-pushed (delete + insert) if its
    actual start/end on the calendar no longer matches what the parser set —
    e.g. someone manually dragged it to a new time. We never PATCH an event in
    place, only delete stale ones and insert fresh ones.
    """
    existing = fetch_existing_events(service, calendar_id, source)
    fetched = {e.unique_key: e for e in events}
    stats = {"inserted": 0, "deleted": 0, "skipped": 0, "errors": 0}

    for key, event in fetched.items():
        if key in existing and event_time_matches(existing[key], event):
            stats["skipped"] += 1
            continue
        if key in existing:
            try:
                delete_event(service, calendar_id, existing[key]["id"])
                stats["deleted"] += 1
                time.sleep(_API_DELAY)
            except Exception as exc:
                logger.error(f"Delete failed for drifted event '{event.name}': {exc}")
                stats["errors"] += 1
                issues.append({"calendar": calendar_name, "source": source, "message": f"Delete failed for '{event.name}': {exc}"})
                # Skip the insert below — the stale event is still on the
                # calendar, so inserting now would create a duplicate.
                continue
        try:
            insert_event(service, calendar_id, event)
            stats["inserted"] += 1
            time.sleep(_API_DELAY)
        except Exception as exc:
            logger.error(f"Insert failed for '{event.name}': {exc}")
            stats["errors"] += 1
            issues.append({"calendar": calendar_name, "source": source, "message": f"Insert failed for '{event.name}': {exc}"})

    for key, existing_event in existing.items():
        if key in fetched:
            continue
        try:
            delete_event(service, calendar_id, existing_event["id"])
            stats["deleted"] += 1
            time.sleep(_API_DELAY)
        except Exception as exc:
            logger.error(f"Delete failed for key '{key}': {exc}")
            stats["errors"] += 1
            issues.append({"calendar": calendar_name, "source": source, "message": f"Delete failed for '{key}': {exc}"})

    return stats


def run_sync(
    num_events_per_source: int | None = None,
    delete_parser_events: bool = False,
    delete_all_events_before_push: bool = False,
    source: str | None = None,
    issues: List[dict] | None = None,
) -> None:
    if issues is None:
        issues = []
    creds = get_credentials()
    service = build_service(creds)
    run_started_at = datetime.now(tz=_TZ)
    run_id = run_started_at.isoformat()

    for calendar_name, scraper_names in CALENDARS.items():
        logger.info(f"=== Calendar: {calendar_name} ===")
        calendar_id = CALENDAR_IDS[calendar_name]

        if delete_parser_events:
            deleted_keys = delete_all_parser_events(service, calendar_id, source=source)
            logger.info(f"[{calendar_name}] deleted parser events={len(deleted_keys)}")
            continue

        if delete_all_events_before_push:
            deleted_keys = delete_all_parser_events(service, calendar_id, source=source)
            logger.info(f"[{calendar_name}] deleted parser events before push={len(deleted_keys)}")

        dedup_rule = DEDUP_RULES.get(calendar_name, DEFAULT_DEDUP_RULE)
        dup_count = delete_duplicate_events(
            service,
            calendar_id,
            fields=dedup_rule["fields"],
            time_window_minutes=dedup_rule["time_window_minutes"],
        )
        if dup_count:
            logger.info(f"[{calendar_name}] removed duplicate events={dup_count}")

        for name in scraper_names:
            fetched = _fetch_safe(name, calendar_name, issues)
            emit_metric("scraper_fetch", source=name, calendar=calendar_name, count=len(fetched))
            if num_events_per_source is not None:
                fetched = fetched[:num_events_per_source]

            deduped: dict[str, Event] = {e.unique_key: e for e in fetched}
            events = _filter_events(list(deduped.values()))
            logger.info(f"[{calendar_name}/{name}] {len(events)} events after date filtering")

            stats = _sync_source(service, calendar_id, calendar_name, name, events, issues)
            logger.info(
                f"[{calendar_name}/{name}] "
                f"inserted={stats['inserted']} deleted={stats['deleted']} "
                f"skipped={stats['skipped']} errors={stats['errors']}"
            )

            for action in ("inserted", "deleted", "skipped", "errors"):
                emit_metric("sync_result", source=name, calendar=calendar_name, action=action, count=stats[action])
            record_stats(run_id, run_started_at, calendar_name, name, stats)

        old_deleted = delete_events_older_than(service, calendar_id, days=3)
        logger.info(f"[{calendar_name}] deleted old events={old_deleted}")

    if not delete_parser_events:
        snapshot_records = []
        for calendar_name, calendar_id in CALENDAR_IDS.items():
            for event in fetch_all_events(service, calendar_id, days_ahead=_SNAPSHOT_LOOKAHEAD_DAYS):
                record = _snapshot_record(calendar_name, event)
                if record:
                    snapshot_records.append(record)
        write_snapshot(run_id, run_started_at, snapshot_records)

    if issues:
        subject, body = format_parsing_issues_email(issues, run_started_at)
        send_error_email(subject, body)
