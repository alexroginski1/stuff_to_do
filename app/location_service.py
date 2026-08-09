from __future__ import annotations

import logging

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)

NOT_FOUND = "Location Not Found"

_USER_AGENT = "stuff-to-do-sf-events-sync"
# [(south-west), (north-east)] — biases Nominatim toward SF without excluding
# events that are genuinely just outside it (e.g. Berkeley, Oakland).
_SF_VIEWBOX = [(37.708, -122.535), (37.834, -122.355)]

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

    result = None
    try:
        result = _geocode(
            raw, addressdetails=True, viewbox=_SF_VIEWBOX, bounded=True, exactly_one=True
        )
    except Exception as exc:
        logger.warning(f"Geocoding lookup failed for {raw!r}: {exc}")

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
