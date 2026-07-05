from __future__ import annotations

import logging

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "sync_stats"
_client: firestore.Client | None = None


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def record_stats(run_id: str, calendar: str, source: str, stats: dict) -> None:
    """Append one run's stats for a single calendar/source to Firestore.

    Each call adds a new document (never overwrites), so the collection
    accumulates a history of every scheduler run for the public stats API.
    Failures are logged, not raised — a Firestore hiccup shouldn't fail an
    otherwise-successful sync run.
    """
    try:
        _get_client().collection(_COLLECTION).add({
            "run_id": run_id,
            "calendar": calendar,
            "source": source,
            "inserted": stats["inserted"],
            "deleted": stats["deleted"],
            "skipped": stats["skipped"],
            "errors": stats["errors"],
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        logger.error(f"Failed to record stats for {calendar}/{source} to Firestore: {exc}")
