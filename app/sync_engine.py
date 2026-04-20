from __future__ import annotations

import importlib
import logging
import time
from typing import List

from app.calendar_service import (
    build_service,
    fetch_existing_events,
    get_credentials,
    get_or_create_calendar,
    insert_event,
    update_event,
)
from app.event_model import Event
from config.settings import CALENDARS

logger = logging.getLogger(__name__)

_API_DELAY = 0.1  # seconds between Google Calendar write calls


def _fetch_safe(scraper_name: str) -> List[Event]:
    try:
        module = importlib.import_module(f"scrapers.{scraper_name}")
        events = module.fetch_events()
        logger.info(f"[{scraper_name}] fetched {len(events)} events")
        return events
    except Exception as exc:
        logger.error(f"[{scraper_name}] scraper failed: {exc}", exc_info=True)
        return []


def _sync_calendar(service, calendar_id: str, events: List[Event]) -> dict:
    existing = fetch_existing_events(service, calendar_id)
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    for event in events:
        key = event.unique_key
        try:
            if key not in existing:
                insert_event(service, calendar_id, event)
                stats["inserted"] += 1
                time.sleep(_API_DELAY)
            elif existing[key]["content_hash"] != event.content_hash():
                update_event(service, calendar_id, existing[key]["event_id"], event)
                stats["updated"] += 1
                time.sleep(_API_DELAY)
            else:
                stats["skipped"] += 1
        except Exception as exc:
            logger.error(f"Sync failed for '{event.name}': {exc}")
            stats["errors"] += 1

    return stats


def run_sync() -> None:
    creds = get_credentials()
    service = build_service(creds)

    for calendar_name, scraper_names in CALENDARS.items():
        logger.info(f"=== Calendar: {calendar_name} ===")
        calendar_id = get_or_create_calendar(service, calendar_name)

        raw_events: List[Event] = []
        for name in scraper_names:
            raw_events.extend(_fetch_safe(name))

        # Deduplicate by unique_key; last occurrence wins (shouldn't matter in practice)
        deduped: dict[str, Event] = {}
        for e in raw_events:
            deduped[e.unique_key] = e

        events = list(deduped.values())
        logger.info(f"[{calendar_name}] {len(events)} unique events to sync")

        stats = _sync_calendar(service, calendar_id, events)
        logger.info(
            f"[{calendar_name}] inserted={stats['inserted']} "
            f"updated={stats['updated']} skipped={stats['skipped']} "
            f"errors={stats['errors']}"
        )
