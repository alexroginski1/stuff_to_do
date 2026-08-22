from __future__ import annotations

import hashlib
import logging

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "neighborhood_cache"
_client: firestore.Client | None = None


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def _doc_id(address: str) -> str:
    normalized = address.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_cached_neighborhood(address: str) -> tuple[bool, str | None]:
    """Return (cache_hit, neighborhood) for `address`.

    `neighborhood` is None both on a cache miss and when `address` is known
    to resolve outside every SF neighborhood boundary — `cache_hit`
    disambiguates the two. Also returns (False, None) if Firestore is
    unreachable, so callers fall back to a fresh geocode.
    """
    try:
        doc = _get_client().collection(_COLLECTION).document(_doc_id(address)).get()
    except Exception as exc:
        logger.error(f"Failed to read neighborhood cache for {address!r}: {exc}")
        return False, None
    if not doc.exists:
        return False, None
    return True, (doc.to_dict() or {}).get("neighborhood") or None


def save_neighborhood(address: str, neighborhood: str | None) -> None:
    """Persist a resolved neighborhood (or None, meaning outside SF) for `address`, keyed for reuse by every future run."""
    try:
        _get_client().collection(_COLLECTION).document(_doc_id(address)).set({
            "address": address,
            "neighborhood": neighborhood,
            "resolved_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        logger.error(f"Failed to write neighborhood cache for {address!r}: {exc}")
