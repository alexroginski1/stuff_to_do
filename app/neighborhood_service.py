from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from shapely.geometry import Point, shape

logger = logging.getLogger(__name__)

# DataSF "Analysis Neighborhoods" (41 official SF neighborhoods, grouped from
# 2010 Census tracts): https://data.sfgov.org/d/j2bu-swwd
_GEOJSON_PATH = Path(__file__).parent / "data" / "sf_neighborhoods.geojson"

_boundaries: list[tuple[str, object]] | None = None
_name_lookup: dict[str, str] | None = None

# Trailing/leading words stripped during normalization since they're
# routinely tacked onto a neighborhood name without changing which
# neighborhood is meant (e.g. "Mission District" -> "Mission").
_STRIP_LEADING_WORDS = {"the"}
_STRIP_TRAILING_WORDS = {"district", "neighborhood", "area"}


def _normalize(text: str) -> str:
    text = re.sub(r"[/\-]", " ", text.lower())
    text = re.sub(r"[^a-z0-9 ]", "", text)
    words = text.split()
    if words and words[0] in _STRIP_LEADING_WORDS:
        words = words[1:]
    if len(words) > 1 and words[-1] in _STRIP_TRAILING_WORDS:
        words = words[:-1]
    return " ".join(words)


def _load_boundaries() -> list[tuple[str, object]]:
    global _boundaries
    if _boundaries is None:
        try:
            data = json.loads(_GEOJSON_PATH.read_text())
            _boundaries = [
                (feature["properties"]["nhood"], shape(feature["geometry"]))
                for feature in data["features"]
            ]
        except Exception as exc:
            logger.error(f"Failed to load SF neighborhood boundaries: {exc}")
            _boundaries = []
    return _boundaries


def neighborhood_for(lat: float, lon: float) -> str | None:
    """Return the SF neighborhood containing (lat, lon), or None if it falls outside all of them.

    A None result is expected, not an error, for any event outside San
    Francisco proper (Oakland, Berkeley, etc.) — the boundaries only cover SF.
    """
    point = Point(lon, lat)  # GeoJSON coordinate order is (lon, lat).
    for name, polygon in _load_boundaries():
        if polygon.contains(point):
            return name
    return None


def neighborhood_name_match(text: str) -> str | None:
    """Return the canonical SF neighborhood name if `text` itself names one of the 41 neighborhoods, or None.

    Pure local string matching (normalized, exact match only — no
    geocoding, no fuzzy matching) against the same boundary dataset used by
    `neighborhood_for`. E.g. "Mission District" -> "Mission". A colloquial
    name that isn't the literal (normalized) official name — e.g. "the
    Castro" for "Castro/Upper Market" — won't match. Meant for an "inexact"
    location string that names an area rather than a specific address (see
    `location_service.resolve_location`).
    """
    global _name_lookup
    if _name_lookup is None:
        _name_lookup = {_normalize(name): name for name, _ in _load_boundaries()}
    normalized = _normalize(text)
    if not normalized:
        return None
    return _name_lookup.get(normalized)
