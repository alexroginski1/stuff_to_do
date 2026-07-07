from __future__ import annotations

import importlib
import logging
import time
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from app.calendar_service import (
    build_service,
    delete_all_events,
    delete_all_parser_events,
    delete_duplicate_events,
    delete_event,
    delete_events_older_than,
    event_time_matches,
    fetch_existing_events,
    get_credentials,
    insert_event,
)

from app.event_model import Event
from app.stats_store import record_stats
from app.utils import emit_metric
from config.settings import CALENDARS, CALENDAR_IDS

logger = logging.getLogger(__name__)

_API_DELAY = 0.1  # seconds between Google Calendar write calls
_TZ = ZoneInfo("America/Los_Angeles")
_LOOKAHEAD_DAYS = 14  # 2 weeks


def _filter_events(events: List[Event]) -> List[Event]:
    today = datetime.now(tz=_TZ).date()
    cutoff = today + timedelta(days=_LOOKAHEAD_DAYS)
    kept = []
    for e in events:
        event_date = e.start_time.astimezone(_TZ).date()
        if event_date < today:
            continue
        if event_date > cutoff:
            continue
        kept.append(e)
    return kept


def _fetch_safe(scraper_name: str) -> List[Event]:
    try:
        module = importlib.import_module(f"scrapers.{scraper_name}")
        events = module.fetch_events()
        logger.info(f"[{scraper_name}] fetched {len(events)} events")
        return events
    except Exception as exc:
        logger.error(f"[{scraper_name}] scraper failed: {exc}", exc_info=True)
        return []


def _sync_source(service, calendar_id: str, source: str, events: List[Event]) -> dict:
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

    return stats


def run_sync(
    num_events_per_source: int | None = None,
    delete_parser_events: bool = False,
    delete_all_events_flag: bool = False,
    source: str | None = None,
) -> None:
    creds = get_credentials()
    service = build_service(creds)
    run_started_at = datetime.now(tz=_TZ)
    run_id = run_started_at.isoformat()

    for calendar_name, scraper_names in CALENDARS.items():
        logger.info(f"=== Calendar: {calendar_name} ===")
        calendar_id = CALENDAR_IDS[calendar_name]

        if delete_all_events_flag:
            deleted = delete_all_events(service, calendar_id, source=source)
            logger.info(f"[{calendar_name}] deleted all events={deleted}")
            continue

        if delete_parser_events:
            deleted_keys = delete_all_parser_events(service, calendar_id, source=source)
            logger.info(f"[{calendar_name}] deleted parser events={len(deleted_keys)}")
            continue

        dup_count = delete_duplicate_events(service, calendar_id)
        if dup_count:
            logger.info(f"[{calendar_name}] removed duplicate events={dup_count}")

        for name in scraper_names:
            fetched = _fetch_safe(name)
            emit_metric("scraper_fetch", source=name, calendar=calendar_name, count=len(fetched))
            if num_events_per_source is not None:
                fetched = fetched[:num_events_per_source]

            deduped: dict[str, Event] = {e.unique_key: e for e in fetched}
            events = _filter_events(list(deduped.values()))
            logger.info(f"[{calendar_name}/{name}] {len(events)} events after date filtering")

            stats = _sync_source(service, calendar_id, name, events)
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
