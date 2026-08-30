from __future__ import annotations

import logging
import os
import re

import requests

from app.inexact_match_override_store import find_override
from app.location_cache_store import get_cached_location, save_location
from app.location_stats_store import record_api_call, record_cache_hit, record_manual_override
from app.neighborhood_service import neighborhood_for, neighborhood_name_match

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

# Sprawling open-space types where Places free-text search tends to match the
# whole feature (e.g. all of Golden Gate Park) instead of the specific venue
# named in the query — the address is technically real but far too coarse to
# be useful as "the" location.
_LOW_PRECISION_TYPES = {"park", "natural_feature", "campground"}

# Raw strings that describe a virtual/no-location event rather than a place —
# never worth spending a Places lookup on, since any result would be wrong.
_VIRTUAL_LOCATION_STRINGS = {"online", "online event", "virtual", "virtual event"}

# Words too common to count as evidence that a Places result actually matches
# what `raw` was describing.
_GENERIC_WORDS = {
    "the", "and", "at", "in", "on", "of", "san", "francisco", "oakland",
    "berkeley", "usa", "ca", "st", "street", "ave", "avenue", "blvd",
}

# Cache of this run's resolutions, keyed by raw string, layered in front of
# the persistent Firestore cache to avoid a redundant DB read for a venue
# string that repeats across many events in the same run.
_cache: dict[str, tuple[str, str, tuple[float, float] | None]] = {}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z']{3,}", text.lower())
    return {w for w in words if w not in _GENERIC_WORDS}


def _looks_related(raw: str, result: dict) -> bool:
    """Whether a Places result plausibly matches what `raw` was describing.

    Free-text search on a bare venue/area name (no street number to anchor
    it) will still confidently return *some* result even when nothing
    relevant exists nearby, so it's not enough to check that a result came
    back — it has to actually reference something from `raw`.
    """
    haystack = f"{result.get('name', '')} {result.get('formatted_address', '')}".lower()
    words = _significant_words(raw)
    return not words or any(word in haystack for word in words)


def _is_city_level_address(formatted_address: str) -> bool:
    """Whether `formatted_address` is just "City, State ZIP[, Country]" with
    no street, venue, or landmark detail — i.e. no more specific than saying
    "somewhere in San Francisco", which the raw string already implied.
    """
    parts = [p.strip() for p in formatted_address.split(",") if p.strip()]
    if parts and parts[-1].upper() == "USA":
        parts = parts[:-1]
    return len(parts) <= 2


def _within_bay_area(lat: float, lon: float) -> bool:
    lat_lo, lat_hi = _BAY_AREA_BOUNDS["lat"]
    lon_lo, lon_hi = _BAY_AREA_BOUNDS["lon"]
    return lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi


def _places_text_search(query: str, api_key: str) -> tuple[dict | None, bool]:
    """Run the Places text search, returning (top_result_or_None, api_call_succeeded).

    `api_call_succeeded` is False only when the request itself didn't
    complete (network error, non-OK/non-ZERO_RESULTS status) — a transient
    problem worth retrying next run. A `ZERO_RESULTS` status is a completed,
    trustworthy answer ("Places has nothing for this query"), so it comes
    back as `(None, True)`.
    """
    record_api_call()
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
        return None, False

    status = data.get("status")
    if status == "ZERO_RESULTS":
        return None, True
    if status != "OK":
        logger.warning(
            f"Google Places lookup for {query!r} returned status={status}: "
            f"{data.get('error_message')}"
        )
        return None, False

    results = data.get("results") or []
    return (results[0] if results else None), True


def _resolve_via_places(raw: str) -> tuple[str, str, tuple[float, float] | None, bool]:
    """Resolve `raw` via Places.

    Returns (cleaned_location, location_type, coords, cacheable). `cacheable`
    is False only when the lookup didn't actually complete (missing API key,
    network/HTTP failure) — those are worth retrying next run. Every other
    NOT_FOUND outcome (Places ran and found nothing usable) is a real,
    stable answer and is cacheable so it isn't re-queried.
    """
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        logger.error("GOOGLE_PLACES_API_KEY not configured; skipping location resolution")
        return NOT_FOUND, "inexact", None, False

    result, succeeded = _places_text_search(raw, api_key)
    if not succeeded:
        return NOT_FOUND, "inexact", None, False
    if result is None:
        return NOT_FOUND, "inexact", None, True

    location = (result.get("geometry") or {}).get("location") or {}
    try:
        lat, lon = float(location["lat"]), float(location["lng"])
    except (KeyError, TypeError, ValueError):
        return NOT_FOUND, "inexact", None, True
    if not _within_bay_area(lat, lon):
        return NOT_FOUND, "inexact", None, True

    formatted_address = result.get("formatted_address")
    if not formatted_address:
        return NOT_FOUND, "inexact", None, True

    types = set(result.get("types") or [])
    if types & _AREA_TYPES or types & _LOW_PRECISION_TYPES:
        return raw, "inexact", None, True
    if _is_city_level_address(formatted_address):
        return raw, "inexact", None, True
    if not any(ch.isdigit() for ch in raw) and not _looks_related(raw, result):
        # `raw` has no street number to anchor the search, and this result
        # doesn't reference anything from it — likely an unrelated same-ish
        # named place (Places has to return something), not a real match.
        return raw, "inexact", None, True
    return formatted_address, "exact", (lat, lon), True


def resolve_location(raw_location: str | None) -> tuple[str, str, tuple[float, float] | None]:
    """Resolve `raw_location` to a full address via Google Places, backed by a persistent cache.

    Returns (cleaned_location, location_type, coords). `location_type` is
    "inexact" when the input names an area (neighborhood, city, etc.)
    rather than a specific address/venue, when the only Places match is too
    coarse or too unreliable to trust (see `_resolve_via_places`), or when
    nothing resolves — in which case cleaned_location is NOT_FOUND. When
    inexact but resolved, cleaned_location is `raw_location` itself (e.g.
    "Mission District" stays "Mission District", not whatever place
    Google's search happened to rank first). Otherwise it's "exact" and
    cleaned_location is the full address Places returned. `coords` is the
    (lat, lon) Places resolved for an "exact" result — so a caller that also
    wants the neighborhood (see `resolve_neighborhood`) can look it up
    locally instead of geocoding the address a second time — or None for
    every "inexact"/NOT_FOUND result and for a cache hit predating coords
    being cached (retried next run, same as any other cache miss shape).

    Every distinct raw string is only ever sent to the Places API once: any
    outcome where the lookup actually completed — an exact/inexact match, or
    a confirmed "nothing usable" NOT_FOUND — is saved to Firestore
    (location_cache_store) so every later lookup for that same string — this
    run or any future one — is a database read instead of a billed API call.
    Only a NOT_FOUND caused by the lookup itself failing to complete (no API
    key configured, network/HTTP error) is left uncached, so a transient
    problem doesn't permanently poison the cache; that case alone is retried
    next run.

    Before an "inexact" answer (freshly resolved, or already sitting in the
    cache from a previous run) is returned, it's checked against the
    inexact_match_manual_update sheet (app/inexact_match_override_store.py)
    — a manually-curated list of raw strings Places can't resolve well,
    mapped to the correct address. A match there is treated as "exact",
    saved to the location cache like any other resolution, and logged via
    record_manual_override for the /manual-location-overrides page — without
    ever calling Places, since the sheet's answer is already known-good.
    """
    raw = (raw_location or "").strip()
    if not raw:
        return NOT_FOUND, "inexact", None
    if raw.lower() in _VIRTUAL_LOCATION_STRINGS:
        return NOT_FOUND, "inexact", None
    if raw in _cache:
        record_cache_hit()
        return _cache[raw]

    cached = get_cached_location(raw)
    if cached is not None and cached[1] != "inexact":
        _cache[raw] = cached
        record_cache_hit()
        return cached

    override = find_override(raw)
    if override is not None:
        resolved = (override, "exact", None)
        _cache[raw] = resolved
        save_location(raw, override, "exact", None)
        record_manual_override(raw, override)
        return resolved

    if cached is not None:
        _cache[raw] = cached
        record_cache_hit()
        return cached

    cleaned, location_type, coords, cacheable = _resolve_via_places(raw)
    resolved = (cleaned, location_type, coords)
    _cache[raw] = resolved
    if cacheable:
        save_location(raw, cleaned, location_type, coords)
    return resolved


def resolve_neighborhood(
    cleaned_location: str, location_type: str, coords: tuple[float, float] | None
) -> str | None:
    """Return the SF neighborhood for an already-resolved location, or None. Never calls an API.

    For an "exact" location, does a local point-in-polygon lookup against
    `coords` — the lat/lon `resolve_location` already got from Places while
    resolving it, so this costs no extra geocode. If `coords` is None (an
    "exact" location that skipped Places entirely, e.g. a scraper-verified
    address, or a cache hit from before coords were cached), returns None
    rather than spending an API call just to find the neighborhood.

    For an "inexact" location, returns a neighborhood only when
    `cleaned_location` itself names one of the 41 SF neighborhoods (e.g.
    "Mission District") via `neighborhood_name_match` — pure string
    matching, not geocoding. Any other area name (a city, "Online",
    NOT_FOUND) returns None.
    """
    if location_type == "exact":
        return neighborhood_for(*coords) if coords is not None else None
    return neighborhood_name_match(cleaned_location)
