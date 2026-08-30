from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
_TIMEOUT_SECONDS = 6


def geocode_address(address: str) -> tuple[float, float] | None:
    """Look up (lat, lon) for a full US street address via the free Census Bureau geocoder.

    No API key, no cost — used only as a fallback to find the neighborhood
    for an "exact" address that `location_service.resolve_location` already
    resolved without ever calling Google Places (see its
    `_looks_like_full_address` bypass and `Event.location_verified`), so
    there'd otherwise be no lat/lon to run through
    `neighborhood_service.neighborhood_for`.

    Returns None on any failure — network error, timeout, or no match. The
    geocoder's own gateway returns an occasional transient error; a failed
    lookup here just means the address is retried on a later scheduler run
    rather than blocking this one.
    """
    try:
        resp = requests.get(
            _GEOCODE_URL,
            params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning(f"Census geocoder failed for {address!r}: {exc}")
        return None

    matches = (data.get("result") or {}).get("addressMatches") or []
    if not matches:
        return None
    coords = matches[0].get("coordinates") or {}
    try:
        return float(coords["y"]), float(coords["x"])
    except (KeyError, TypeError, ValueError):
        return None
