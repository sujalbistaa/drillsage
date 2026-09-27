"""Georeferencing: ED50 geographic → WGS84 geographic and WGS84 / UTM projected coordinates.

pyproj applies the EPSG default ED50→WGS84 transformation (Helmert, accurate to a few metres),
which is well inside what offset-well selection needs. Survey azimuths are treated as grid
azimuths in the projected CRS; at Volve the grid convergence is under 1°.
"""

from dataclasses import dataclass
from functools import cache

from pyproj import CRS, Transformer

_GEOGRAPHIC_EPSG = {"ED50": 4230, "WGS84": 4326, "ETRS89": 4258}


@dataclass(frozen=True, slots=True)
class SurfaceLocation:
    lat_deg: float
    lon_deg: float
    """WGS84 geographic."""
    easting_m: float
    northing_m: float
    utm_epsg: int
    """WGS84 / UTM zone the easting/northing are expressed in."""


def utm_epsg_for(lon_deg: float, lat_deg: float) -> int:
    zone = int((lon_deg + 180.0) // 6.0) + 1
    return (32600 if lat_deg >= 0 else 32700) + zone


@cache
def _transformer(source_epsg: int, target_epsg: int) -> Transformer:
    return Transformer.from_crs(
        CRS.from_epsg(source_epsg), CRS.from_epsg(target_epsg), always_xy=True
    )


def to_wgs84(
    lat_deg: float, lon_deg: float, datum: str, *, utm_epsg: int | None = None
) -> SurfaceLocation:
    """Convert a surface location from `datum` geographic coordinates to WGS84 + UTM."""
    source = _GEOGRAPHIC_EPSG.get(datum.upper())
    if source is None:
        raise ValueError(f"unsupported geodetic datum {datum!r}")
    lon84, lat84 = _transformer(source, 4326).transform(lon_deg, lat_deg)
    epsg = utm_epsg or utm_epsg_for(lon84, lat84)
    easting, northing = _transformer(4326, epsg).transform(lon84, lat84)
    return SurfaceLocation(
        lat_deg=float(lat84),
        lon_deg=float(lon84),
        easting_m=float(easting),
        northing_m=float(northing),
        utm_epsg=epsg,
    )


def utm_to_wgs84(easting_m: float, northing_m: float, utm_epsg: int) -> tuple[float, float]:
    """(lat, lon) in WGS84 for a point in a WGS84 / UTM CRS."""
    lon, lat = _transformer(utm_epsg, 4326).transform(easting_m, northing_m)
    return float(lat), float(lon)
