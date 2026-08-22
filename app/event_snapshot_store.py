from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "event_snapshot"
_BATCH_SIZE = 400  # Firestore batch writes cap at 500 operations.
_client: firestore.Client | None = None


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def write_snapshot(run_id: str, run_started_at: datetime, records: List[dict]) -> None:
    """Replace the event_snapshot collection with the given records.

    Each record is a dict with title/description/start_time/end_time/
    raw_location/cleaned_location/location_type/neighborhood/calendar/
    source_type/source/gcal_id/gcal_link, built from a live Calendar API event
    (app.calendar_service.fetch_all_events) so both parser-created and
    manually-added events are captured. Runs once at the end of every
    scheduler run, so the public "/" page always reflects the calendar's
    actual contents as of the most recent sync without calling the Calendar
    API on page load. Documents are keyed by gcal_id (the Calendar API's own
    event id, unique per event and safe as a Firestore document id, unlike
    the calendar's display name which can contain "/"), which lets this run
    as an upsert-and-prune diff against the previous run's documents rather
    than growing without bound.
    """
    try:
        client = _get_client()
        collection = client.collection(_COLLECTION)
        stale_refs = {doc.id: doc.reference for doc in collection.stream()}

        for i in range(0, len(records), _BATCH_SIZE):
            batch = client.batch()
            for record in records[i : i + _BATCH_SIZE]:
                doc_id = record["gcal_id"]
                doc_ref = collection.document(doc_id)
                batch.set(doc_ref, {
                    "run_id": run_id,
                    "timestamp": run_started_at,
                    "title": record["title"],
                    "description": record["description"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "raw_location": record["raw_location"],
                    "cleaned_location": record["cleaned_location"],
                    "location_type": record["location_type"],
                    "neighborhood": record["neighborhood"],
                    "calendar": record["calendar"],
                    "source_type": record["source_type"],
                    "source": record["source"],
                    "gcal_link": record["gcal_link"],
                })
                stale_refs.pop(doc_id, None)
            batch.commit()

        stale_list = list(stale_refs.values())
        for i in range(0, len(stale_list), _BATCH_SIZE):
            batch = client.batch()
            for ref in stale_list[i : i + _BATCH_SIZE]:
                batch.delete(ref)
            batch.commit()

        logger.info(
            f"Event snapshot updated: {len(records)} events written, "
            f"{len(stale_list)} stale events pruned"
        )
    except Exception as exc:
        logger.error(f"Failed to write event snapshot to Firestore: {exc}")
