"""Basemap tiles embedded in map.html so a Claude artifact can show streets.

A published artifact blocks every external image (img-src is data: and blob:
only; scripts may still come from cdnjs). No tile host is on that allow-list,
so the page cannot load OpenStreetMap.de or Esri at view time. We download a
bounded set of PNG tiles while generating the HTML and inline them as data
URIs. A normal browser still requests live tiles for zoom levels we did not
embed.

Tile servers dislike bulk downloads. One scenario is at most MAX_TILES tiles,
cached under `.cache/map-tiles/`. Failures are warnings: the map still renders,
and a browser can load the live tiles.
"""

from __future__ import annotations

import base64
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

TILE_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
USER_AGENT = "de-pass-routeplanning/busroutes (schoolbus map; local tile embed)"
MAX_TILES = 32
MAX_ZOOM = 16
MIN_ZOOM = 2
# fitBounds centers the routes in the pane, so the visible tiles extend past
# the route bounds. One complete zoom is embedded for a pane larger than the
# stats-panel layout; a partial zoom leaves gray holes where the image was blocked.
ZOOM_PANE = (1040, 800)
COVERAGE_PANE = (1400, 900)
_MIN_SPAN = 0.01  # degrees; a single stop still gets a little context
_PAD = 0.05  # matches Leaflet fitBounds(bounds.pad(0.05))
_PNG = b"\x89PNG"

TileFetcher = Callable[[str], bytes]


class TileError(RuntimeError):
    pass


def tile_cache_dir(tomtom_cache_dir: Path | None) -> Path | None:
    """Sibling of the TomTom cache: `.cache/tomtom` → `.cache/map-tiles`."""
    if tomtom_cache_dir is None:
        return None
    return Path(tomtom_cache_dir).parent / "map-tiles"


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """XYZ tile containing this WGS84 point (same scheme as OSM slippy tiles)."""
    n = 2**zoom
    lat = min(max(lat, -85.05112878), 85.05112878)
    x = int((lon + 180.0) / 360.0 * n)
    rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def _project(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (2**zoom)
    lat = min(max(lat, -85.05112878), 85.05112878)
    rad = math.radians(lat)
    x = (lon + 180.0) / 360.0 * scale
    y = (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * scale
    return x, y


def _coords(geom: dict) -> list[tuple[float, float]]:
    kind = geom.get("type")
    coords = geom.get("coordinates")
    if kind == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return [(float(coords[0]), float(coords[1]))]
    if kind == "LineString" and isinstance(coords, list):
        return [(float(p[0]), float(p[1])) for p in coords if isinstance(p, list) and len(p) >= 2]
    return []


def bounds_from_geojson(geojson: dict) -> tuple[float, float, float, float]:
    """(west, south, east, north), padded so fitBounds stays inside the tiles."""
    pairs: list[tuple[float, float]] = []
    for feature in geojson.get("features") or []:
        pairs.extend(_coords(feature.get("geometry") or {}))
    if not pairs:
        raise TileError("geen coördinaten voor de basiskaart")
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
    if east - west < _MIN_SPAN:
        mid = (east + west) / 2
        west, east = mid - _MIN_SPAN / 2, mid + _MIN_SPAN / 2
    if north - south < _MIN_SPAN:
        mid = (north + south) / 2
        south, north = mid - _MIN_SPAN / 2, mid + _MIN_SPAN / 2
    pad_lon = (east - west) * _PAD
    pad_lat = (north - south) * _PAD
    return west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat


def zoom_to_fit(
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
    max_zoom: int = MAX_ZOOM,
) -> int:
    """Highest zoom at which the bounds fit in a map pane of this size."""
    usable_w = width * (1 - 2 * 0.05)
    usable_h = height * (1 - 2 * 0.05)
    for zoom in range(max_zoom, MIN_ZOOM - 1, -1):
        x0, y0 = _project(west, north, zoom)
        x1, y1 = _project(east, south, zoom)
        if (x1 - x0) <= usable_w and (y1 - y0) <= usable_h:
            return zoom
    return MIN_ZOOM


def tiles_covering(
    west: float, south: float, east: float, north: float, zoom: int
) -> list[tuple[int, int, int]]:
    x0, y_north = tile_xy(west, north, zoom)
    x1, y_south = tile_xy(east, south, zoom)
    y0, y1 = min(y_north, y_south), max(y_north, y_south)
    return [(zoom, x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(y0, y1 + 1)]


def visible_tile_keys(
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
    zoom: int,
) -> list[tuple[int, int, int]]:
    """Tiles a pane shows after fitBounds: the bounds are centered, the rest is margin."""
    x_west, y_north = _project(west, north, zoom)
    x_east, y_south = _project(east, south, zoom)
    center_x = (x_west + x_east) / 2
    center_y = (y_north + y_south) / 2
    left, right = center_x - width / 2, center_x + width / 2
    top, bottom = center_y - height / 2, center_y + height / 2
    n = 2**zoom
    x0 = max(0, math.floor(left / 256))
    x1 = min(n - 1, math.floor((right - 1e-6) / 256))
    y0 = max(0, math.floor(top / 256))
    y1 = min(n - 1, math.floor((bottom - 1e-6) / 256))
    if x1 < x0 or y1 < y0:
        return []
    return [(zoom, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def select_tile_keys(geojson: dict) -> list[tuple[int, int, int]]:
    """One complete zoom for a wide map pane, stepped down until it fits the cap."""
    west, south, east, north = bounds_from_geojson(geojson)
    zoom = zoom_to_fit(west, south, east, north, *ZOOM_PANE)
    width, height = COVERAGE_PANE
    while zoom >= MIN_ZOOM:
        batch = visible_tile_keys(west, south, east, north, width, height, zoom)
        if batch and len(batch) <= MAX_TILES:
            return batch
        zoom -= 1
    return []


def _http_tile(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "image/png"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise TileError(f"tile HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise TileError(f"tile netwerkfout: {exc.reason}") from exc
    if not data.startswith(_PNG):
        raise TileError("tile is geen PNG")
    return data


def _read_png(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(_PNG):
        return None
    return data


def _write_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def load_basemap_tiles(
    geojson: dict,
    tomtom_cache_dir: Path | None,
    fetch: TileFetcher = _http_tile,
) -> tuple[dict[str, str], str | None]:
    """`{"z/x/y": "data:image/png;base64,..."}` plus a warning when nothing (or part) is missing.

    Never raises. An empty dict means the HTML falls back to live tile URLs,
    which a browser can load and a Claude artifact cannot.
    """
    try:
        keys = select_tile_keys(geojson)
    except TileError as exc:
        return {}, str(exc)
    cache = tile_cache_dir(tomtom_cache_dir)
    embedded: dict[str, str] = {}
    failed = 0
    for z, x, y in keys:
        path = cache / str(z) / str(x) / f"{y}.png" if cache is not None else None
        png = _read_png(path) if path is not None else None
        if png is None:
            url = TILE_URL.format(z=z, x=x, y=y)
            try:
                png = fetch(url)
            except TileError:
                failed += 1
                continue
            if not png.startswith(_PNG):
                failed += 1
                continue
            if path is not None:
                _write_png(path, png)
        encoded = base64.b64encode(png).decode("ascii")
        embedded[f"{z}/{x}/{y}"] = f"data:image/png;base64,{encoded}"
    if not embedded:
        return {}, "geen basiskaart-tiles opgehaald"
    if failed:
        return embedded, f"{failed} van {len(keys)} basiskaart-tiles ontbreken"
    return embedded, None
