from __future__ import annotations

import hashlib
import logging

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "location_cache"
_client: firestore.Client | None = None


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def _doc_id(raw_location: str) -> str:
    """Firestore document id for `raw_location`, keyed on its normalized form.

    Hashed rather than used directly since raw venue strings often contain
    "/" (illegal in a Firestore document id) and normalizing case/whitespace
    first means "The Independent" and "the independent " share one entry.
    """
    normalized = raw_location.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_cached_location(raw_location: str) -> tuple[str, str, tuple[float, float] | None] | None:
    """Return a previously-saved (cleaned_location, location_type, coords) for `raw_location`, or None on a cache miss.

    `coords` is None for a document written before coords were cached
    alongside the location — treated the same as "unknown", not re-fetched,
    since resolving it would cost the very API call this cache exists to
    avoid; it's simply left out of the neighborhood lookup for that entry.

    Also returns None (rather than raising) if Firestore is unreachable, so
    callers always fall back to a fresh Google Places lookup.
    """
    try:
        doc = _get_client().collection(_COLLECTION).document(_doc_id(raw_location)).get()
    except Exception as exc:
        logger.error(f"Failed to read location cache for {raw_location!r}: {exc}")
        return None
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    cleaned_location = data.get("cleaned_location")
    location_type = data.get("location_type")
    if not cleaned_location or not location_type:
        return None
    lat, lon = data.get("lat"), data.get("lon")
    coords = (lat, lon) if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) else None
    return cleaned_location, location_type, coords


def save_location(
    raw_location: str,
    cleaned_location: str,
    location_type: str,
    coords: tuple[float, float] | None,
) -> None:
    """Persist a resolved (cleaned_location, location_type, coords) for `raw_location`, keyed for reuse by every future run."""
    try:
        doc = {
            "raw_location": raw_location,
            "cleaned_location": cleaned_location,
            "location_type": location_type,
            "resolved_at": firestore.SERVER_TIMESTAMP,
        }
        if coords is not None:
            doc["lat"], doc["lon"] = coords
        _get_client().collection(_COLLECTION).document(_doc_id(raw_location)).set(doc)
    except Exception as exc:
        logger.error(f"Failed to write location cache for {raw_location!r}: {exc}")
