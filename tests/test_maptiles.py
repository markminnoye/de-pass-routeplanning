"""Basemap tile selection and embedding. No network: the fetcher is injected."""

from __future__ import annotations

import base64
import math

import pytest

from busroutes.maptiles import (
    MAX_TILES,
    TileError,
    bounds_from_geojson,
    load_basemap_tiles,
    select_tile_keys,
    tile_xy,
    tiles_covering,
    visible_tile_keys,
    zoom_to_fit,
)

# 1x1 PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

WIDE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[4.70, 50.88], [4.95, 50.75]]},
            "properties": {},
        }
    ],
}

CLOSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[4.890, 50.780], [4.900, 50.786]]},
            "properties": {},
        }
    ],
}


def test_tile_xy_roundtrip_for_a_tile_center():
    zoom, x, y = 12, 2100, 1372
    n = 2**zoom
    lon = (x + 0.5) / n * 360.0 - 180.0
    merc = math.pi * (1 - 2 * (y + 0.5) / n)
    lat = math.degrees(math.atan(math.sinh(merc)))
    assert tile_xy(lon, lat, zoom) == (x, y)


def test_wider_pane_does_not_zoom_out():
    west, south, east, north = bounds_from_geojson(WIDE)
    small = zoom_to_fit(west, south, east, north, 700, 560)
    wide = zoom_to_fit(west, south, east, north, 1400, 900)
    assert wide >= small


def test_select_stays_within_the_tile_cap():
    wide_keys = select_tile_keys(WIDE)
    close_keys = select_tile_keys(CLOSE)
    assert 1 <= len(wide_keys) <= MAX_TILES
    assert 1 <= len(close_keys) <= MAX_TILES
    assert max(z for z, _, _ in close_keys) > max(z for z, _, _ in wide_keys)


def test_selected_zoom_covers_the_map_pane():
    west, south, east, north = bounds_from_geojson(WIDE)
    keys = select_tile_keys(WIDE)
    zoom = keys[0][0]
    assert {z for z, _, _ in keys} == {zoom}
    needed = set(visible_tile_keys(west, south, east, north, 1040, 813, zoom))
    assert needed <= set(keys)


def test_visible_tiles_include_every_bounds_tile():
    west, south, east, north = bounds_from_geojson(WIDE)
    zoom = zoom_to_fit(west, south, east, north, 1040, 813)
    visible = set(visible_tile_keys(west, south, east, north, 1040, 813, zoom))
    assert set(tiles_covering(west, south, east, north, zoom)) <= visible


def test_bounds_require_coordinates():
    with pytest.raises(TileError):
        bounds_from_geojson({"type": "FeatureCollection", "features": []})


def test_load_embeds_pngs_and_reuses_the_disk_cache(tmp_path):
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return PNG

    tiles, warning = load_basemap_tiles(CLOSE, tmp_path / "tomtom", fetch=fetch)
    assert warning is None
    assert tiles
    assert all(value.startswith("data:image/png;base64,") for value in tiles.values())
    assert all(
        url.startswith("https://tile.openstreetmap.de/") and url.endswith(".png") for url in calls
    )
    first = list(calls)
    again, again_warning = load_basemap_tiles(CLOSE, tmp_path / "tomtom", fetch=fetch)
    assert again_warning is None
    assert again == tiles
    assert calls == first


def test_load_warns_instead_of_raising_when_the_tile_server_fails(tmp_path):
    def fetch(url: str) -> bytes:
        raise TileError(f"down {url}")

    tiles, warning = load_basemap_tiles(CLOSE, tmp_path / "tomtom", fetch=fetch)
    assert tiles == {}
    assert warning == "geen basiskaart-tiles opgehaald"


def test_load_keeps_the_tiles_that_did_download():
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if len(calls) == 1:
            raise TileError("missing")
        return PNG

    tiles, warning = load_basemap_tiles(CLOSE, None, fetch=fetch)
    assert tiles
    assert warning is not None
    assert "ontbreken" in warning
    assert len(tiles) == len(calls) - 1
