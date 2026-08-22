from __future__ import annotations

import json
import logging
from pathlib import Path

from shapely.geometry import Point, shape

logger = logging.getLogger(__name__)

# DataSF "Analysis Neighborhoods" (41 official SF neighborhoods, grouped from
# 2010 Census tracts): https://data.sfgov.org/d/j2bu-swwd
_GEOJSON_PATH = Path(__file__).parent / "data" / "sf_neighborhoods.geojson"

_boundaries: list[tuple[str, object]] | None = None


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
