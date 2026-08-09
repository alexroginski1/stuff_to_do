from __future__ import annotations

import logging

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)

NOT_FOUND = "Location Not Found"

_USER_AGENT = "stuff-to-do-sf-events-sync"
# [(south-west), (north-east)] — biases Nominatim toward SF. Only used to bias
# ranking (never with `bounded=True` beyond the first attempt below), since a
# hard bound excludes events that are genuinely just outside SF proper (e.g.
# Berkeley, Oakland, Albany, Vallejo).
_SF_VIEWBOX = [(37.708, -122.535), (37.834, -122.355)]

# Sanity bound for fallback lookups that run without `bounded=True` (see
# `_within_bay_area` below). Nominatim's free-text search can otherwise
# return an unrelated same-named place anywhere on Earth — e.g. "5 Olive
# Gallery" resolving to a street in Los Angeles, or "Union Square area"
# resolving to a plaza in Romania — which is worse than NOT_FOUND because it
# looks authoritative. Loosely covers the greater SF Bay Area.
_BAY_AREA_BOUNDS = {"lat": (36.8, 38.9), "lon": (-123.3, -121.3)}

# Nominatim `addresstype` values that describe an area rather than a single
# building/venue/address — these are the "neighborhood name" case.
_INEXACT_ADDRESS_TYPES = {
    "neighbourhood", "suburb", "quarter", "city_district", "borough",
    "district", "residential", "village", "town", "city", "county",
    "state", "hamlet", "region",
}

# `address` dict keys (from addressdetails=True) that hold an area name
# rather than a specific building/venue, checked in priority order.
_AREA_ADDRESS_FIELDS = [
    "neighbourhood", "suburb", "quarter", "city_district", "borough",
    "village", "town", "hamlet",
]

_geolocator = Nominatim(user_agent=_USER_AGENT, timeout=10)
# Nominatim's usage policy caps free lookups at ~1/sec; this only matters
# within a single sync run since each Cloud Run Job invocation starts fresh.
_geocode = RateLimiter(_geolocator.geocode, min_delay_seconds=1)

_cache: dict[str, tuple[str, str]] = {}


def _matches_area_field(raw: str, address: dict) -> bool:
    """True if any `_AREA_ADDRESS_FIELDS` entry overlaps `raw`.

    Nominatim's free-text search ranks a specifically-named POI ("Mission", a
    sports shop) above the neighborhood boundary it sits in when the query is
    e.g. "Mission District" — the shop isn't what the scraped site meant, but
    its address still carries "suburb": "Mission", which does overlap the
    query. Checking that address hierarchy directly catches the neighborhood
    intent even when the top-ranked match itself is a specific venue.
    """
    raw_lower = raw.lower()
    return any(
        (value := address.get(field)) and value.lower() in raw_lower
        for field in _AREA_ADDRESS_FIELDS
    )


def _within_bay_area(result) -> bool:
    try:
        lat, lon = float(result.raw["lat"]), float(result.raw["lon"])
    except (KeyError, TypeError, ValueError):
        return False
    lat_lo, lat_hi = _BAY_AREA_BOUNDS["lat"]
    lon_lo, lon_hi = _BAY_AREA_BOUNDS["lon"]
    return lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi


def _geocode_query(query: str, *, bounded: bool):
    try:
        return _geocode(
            query, addressdetails=True, viewbox=_SF_VIEWBOX, bounded=bounded, exactly_one=True
        )
    except Exception as exc:
        logger.warning(f"Geocoding lookup failed for {query!r}: {exc}")
        return None


def _candidate_queries(raw: str):
    """Yield progressively looser rewrites of `raw` to retry against Nominatim.

    Scrapers hand us free-text venue strings in wildly different shapes, and
    Nominatim's free-text search is surprisingly brittle about it — e.g. it
    fails on "Ruth Asawa Lanier, Inc. Gallery, 1275 Minnesota Street, San
    Francisco, California, 94107" (venue name prefixed to a full address) but
    succeeds the moment the venue name is dropped, leaving just "1275
    Minnesota Street, San Francisco, California, 94107". So: try the raw
    string first, then repeatedly drop the leading comma-separated segment,
    and finally fall back to the leading segment alone (covers cases like
    "Vesuvio Cafe, Jack Kerouac Alley" where the *tail* is what confuses it).
    """
    yield raw
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    while len(parts) > 2:
        parts = parts[1:]
        yield ", ".join(parts)
    if len(parts) > 1:
        yield parts[0]


def _geocode_with_fallbacks(raw: str):
    """Try `raw`, then looser rewrites of it, each first bounded to SF proper
    and then — only if that fails — unbounded but sanity-checked against the
    wider Bay Area. The bounded attempt runs first and alone handles the
    common case so ranking/behavior for it is unchanged; the unbounded retry
    only kicks in to recover venues genuinely just outside the SF box (e.g.
    Berkeley, Oakland, Albany, Vallejo), and the bounds check keeps it from
    accepting a same-named place on the wrong continent.
    """
    for query in _candidate_queries(raw):
        result = _geocode_query(query, bounded=True)
        if result is None:
            candidate = _geocode_query(query, bounded=False)
            if candidate is not None and _within_bay_area(candidate):
                result = candidate
        if result is not None:
            return result
    return None


def resolve_location(raw_location: str | None) -> tuple[str, str]:
    """Validate `raw_location` against OpenStreetMap/Nominatim and classify its precision.

    Returns (cleaned_location, location_type). `location_type` is "inexact"
    when the input names an area (neighborhood, suburb, city, etc.) rather
    than a specific address/building/venue, or when nothing resolves — in
    which case cleaned_location is NOT_FOUND. When inexact but resolved,
    cleaned_location is `raw_location` itself (e.g. "Mission District" stays
    "Mission District", not Nominatim's own name for that area). Otherwise
    it's "exact" and cleaned_location is the full resolved address. Results
    are cached per raw string for the life of the process, since the same
    venue string repeats across many events in a run.
    """
    raw = (raw_location or "").strip()
    if not raw:
        return NOT_FOUND, "inexact"
    if raw in _cache:
        return _cache[raw]

    result = _geocode_with_fallbacks(raw)

    if result is None:
        resolved = (NOT_FOUND, "inexact")
    else:
        address = result.raw.get("address", {})
        addresstype = result.raw.get("addresstype")

        if _matches_area_field(raw, address) or addresstype in _INEXACT_ADDRESS_TYPES:
            resolved = (raw, "inexact")
        else:
            resolved = (result.address, "exact")

    _cache[raw] = resolved
    return resolved
