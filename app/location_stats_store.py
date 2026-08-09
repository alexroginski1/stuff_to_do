from __future__ import annotations

import logging

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "location_api_stats"
_DOC_ID = "totals"
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
