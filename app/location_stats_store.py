from __future__ import annotations

import hashlib
import logging

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "location_api_stats"
_DOC_ID = "totals"
_MANUAL_OVERRIDES_COLLECTION = "manual_location_overrides"
_client: firestore.Client | None = None


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def _increment(field: str) -> None:
    try:
        _get_client().collection(_COLLECTION).document(_DOC_ID).set(
            {field: firestore.Increment(1)}, merge=True
        )
    except Exception as exc:
        logger.error(f"Failed to increment {field} in location_api_stats: {exc}")


def record_api_call() -> None:
    """Record one live Google Places API request (a billed call)."""
    _increment("api_calls")


def record_cache_hit() -> None:
    """Record one location lookup satisfied by the in-memory or Firestore cache instead of a Places API call."""
    _increment("cache_hits")


def record_manual_override(raw_location: str, exact_location: str) -> None:
    """Log one raw_location -> exact_location conversion applied via the inexact_match_manual_update sheet.

    Backs the /manual-location-overrides page in webapi. Keyed by
    raw_location (same normalization as location_cache_store's doc id) so a
    later run re-applying the same override upserts instead of duplicating
    the log entry.
    """
    try:
        doc_id = hashlib.sha256(raw_location.strip().lower().encode()).hexdigest()
        _get_client().collection(_MANUAL_OVERRIDES_COLLECTION).document(doc_id).set({
            "raw_location": raw_location,
            "exact_location": exact_location,
            "converted_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        logger.error(f"Failed to log manual override for {raw_location!r}: {exc}")
