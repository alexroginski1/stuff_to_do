from __future__ import annotations

import logging
import os

import requests

from app.location_cache_store import get_cached_location, save_location

logger = logging.getLogger(__name__)

NOT_FOUND = "Location Not Found"

_PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
# Biases (never restricts) results toward SF so Places' ranking prefers "the
# venue in San Francisco" over a same-named venue elsewhere.
_SF_BIAS_LOCATION = "37.7749,-122.4194"
_SF_BIAS_RADIUS_METERS = 50_000

# Sanity bound for accepting a Places result — the bias above only affects
# ranking, so free-text search can still return an unrelated same-named place
# anywhere on Earth, which is worse than NOT_FOUND because it looks
# authoritative. Loosely covers the greater SF Bay Area.
_BAY_AREA_BOUNDS = {"lat": (36.8, 38.9), "lon": (-123.3, -121.3)}

# Google Places `types` values that describe an area rather than a single
# building/venue/address — the "neighborhood name" case.
_AREA_TYPES = {
    "locality", "sublocality", "sublocality_level_1", "sublocality_level_2",
    "neighborhood", "administrative_area_level_1", "administrative_area_level_2",
    "administrative_area_level_3", "administrative_area_level_4",
    "administrative_area_level_5", "country", "postal_code", "postal_town",
}

# Cache of this run's resolutions, keyed by raw string, layered in front of
# the persistent Firestore cache to avoid a redundant DB read for a venue
# string that repeats across many events in the same run.
_cache: dict[str, tuple[str, str]] = {}


def _within_bay_area(lat: float, lon: float) -> bool:
    lat_lo, lat_hi = _BAY_AREA_BOUNDS["lat"]
    lon_lo, lon_hi = _BAY_AREA_BOUNDS["lon"]
    return lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi


def _places_text_search(query: str, api_key: str) -> dict | None:
    try:
        resp = requests.get(
            _PLACES_TEXT_SEARCH_URL,
            params={
                "query": query,
                "location": _SF_BIAS_LOCATION,
                "radius": _SF_BIAS_RADIUS_METERS,
                "key": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning(f"Google Places lookup failed for {query!r}: {exc}")
        return None

    status = data.get("status")
    if status != "OK":
        if status != "ZERO_RESULTS":
            logger.warning(
                f"Google Places lookup for {query!r} returned status={status}: "
                f"{data.get('error_message')}"
            )
        return None

    results = data.get("results") or []
    return results[0] if results else None


def _resolve_via_places(raw: str) -> tuple[str, str]:
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        logger.error("GOOGLE_PLACES_API_KEY not configured; skipping location resolution")
        return NOT_FOUND, "inexact"

    result = _places_text_search(raw, api_key)
    if result is None:
        return NOT_FOUND, "inexact"

    location = (result.get("geometry") or {}).get("location") or {}
    try:
        lat, lon = float(location["lat"]), float(location["lng"])
    except (KeyError, TypeError, ValueError):
        return NOT_FOUND, "inexact"
    if not _within_bay_area(lat, lon):
        return NOT_FOUND, "inexact"

    formatted_address = result.get("formatted_address")
    if not formatted_address:
        return NOT_FOUND, "inexact"

    types = set(result.get("types") or [])
    if types & _AREA_TYPES:
        return raw, "inexact"
    return formatted_address, "exact"


def resolve_location(raw_location: str | None) -> tuple[str, str]:
    """Resolve `raw_location` to a full address via Google Places, backed by a persistent cache.

    Returns (cleaned_location, location_type). `location_type` is "inexact"
    when the input names an area (neighborhood, city, etc.) rather than a
    specific address/venue, or when nothing resolves — in which case
    cleaned_location is NOT_FOUND. When inexact but resolved, cleaned_location
    is `raw_location` itself (e.g. "Mission District" stays "Mission
    District", not whatever place Google's search happened to rank first).
    Otherwise it's "exact" and cleaned_location is the full address Places
    returned.

    Every distinct raw string is only ever sent to the Places API once: a
    successful resolution is saved to Firestore (location_cache_store) so
    every later lookup for that same string — this run or any future one —
    is a database read instead of a billed API call. NOT_FOUND results are
    deliberately not persisted, so a transient failure (or a not-yet-set API
    key) doesn't permanently poison the cache; they're retried next run.
    """
    raw = (raw_location or "").strip()
    if not raw:
        return NOT_FOUND, "inexact"
    if raw in _cache:
        return _cache[raw]

    cached = get_cached_location(raw)
    if cached is not None:
        _cache[raw] = cached
        return cached

    resolved = _resolve_via_places(raw)
    _cache[raw] = resolved
    if resolved[0] != NOT_FOUND:
        save_location(raw, resolved[0], resolved[1])
    return resolved
