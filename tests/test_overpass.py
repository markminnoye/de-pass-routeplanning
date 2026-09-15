from pathlib import Path

import pytest

from busroutes.overpass import (
    OverpassError,
    bbox_from_geojson,
    fetch_transit_stops,
    load_transit_overlay,
    overlay_cache_dir,
    parse_overpass,
)

SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [4.90, 50.78]},
            "properties": {"kind": "school"},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[4.90, 50.78], [4.92, 50.80]],
            },
            "properties": {"kind": "route"},
        },
    ],
}

OVERPASS_PAYLOAD = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 50.781,
            "lon": 4.901,
            "tags": {
                "name": "Hoegaarden Gemeentehuis",
                "operator": "De Lijn",
                "ref:De_Lijn": "305001",
            },
        },
        {
            "type": "node",
            "id": 1,
            "lat": 50.781,
            "lon": 4.901,
            "tags": {
                "name": "Hoegaarden Gemeentehuis",
                "operator": "De Lijn",
                "ref:De_Lijn": "305001",
            },
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 50.771, "lon": 4.889},
            "tags": {
                "name": "Jodoigne Gare",
                "operator": "TEC",
                "network": "TECB",
                "ref:TEC": "B1234",
            },
        },
        {
            "type": "node",
            "id": 3,
            "lat": 50.807,
            "lon": 4.939,
            "tags": {
                "name": "Tienen",
                "railway": "station",
                "operator": "NMBS/SNCB",
                "uic_ref": "8832000",
            },
        },
        {
            "type": "node",
            "id": 4,
            "lat": 50.79,
            "lon": 4.91,
            "tags": {"name": "random bench", "amenity": "bench"},
        },
        {
            "type": "node",
            "id": 5,
            "lat": 50.76,
            "lon": 4.87,
            "tags": {"name": "Tourist halt", "railway": "halt", "operator": "CFV3V"},
        },
    ]
}


def test_bbox_pads_scenario_points():
    south, west, north, east = bbox_from_geojson(SAMPLE_GEOJSON)
    assert south < 50.78 < north
    assert west < 4.90 < east
    assert north > 50.80
    assert east > 4.92


def test_bbox_rejects_empty_geojson():
    with pytest.raises(OverpassError):
        bbox_from_geojson({"type": "FeatureCollection", "features": []})


def test_parse_filters_and_dedups_operators():
    gj = parse_overpass(OVERPASS_PAYLOAD)
    kinds = [f["properties"]["operator_kind"] for f in gj["features"]]
    assert kinds == ["delijn", "tec", "nmbs"]
    delijn = gj["features"][0]["properties"]
    assert delijn["ref"] == "305001"
    assert delijn["name"] == "Hoegaarden Gemeentehuis"
    assert delijn["osm_id"] == "node/1"
    assert gj["features"][1]["geometry"]["coordinates"] == [4.889, 50.771]
    assert gj["features"][2]["properties"]["ref"] == "8832000"


def test_fetch_uses_cache_on_second_call(tmp_path: Path):
    calls: list[str] = []

    def fetch(url: str, query: str) -> dict:
        calls.append(url)
        return OVERPASS_PAYLOAD

    bbox = (50.77, 4.88, 50.81, 4.93)
    first = fetch_transit_stops(bbox, tmp_path, fetch=fetch)
    second = fetch_transit_stops(bbox, tmp_path, fetch=fetch)
    assert len(calls) == 1
    assert first == second
    assert len(first["features"]) == 3


def test_fetch_skips_cache_when_dir_is_none():
    calls: list[int] = []

    def fetch(url: str, query: str) -> dict:
        calls.append(1)
        return OVERPASS_PAYLOAD

    bbox = (50.77, 4.88, 50.81, 4.93)
    fetch_transit_stops(bbox, None, fetch=fetch)
    fetch_transit_stops(bbox, None, fetch=fetch)
    assert len(calls) == 2


def test_load_transit_overlay_soft_fails():
    def boom(url: str, query: str) -> dict:
        raise OverpassError("Overpass HTTP 504: timeout")

    stops, warning = load_transit_overlay(SAMPLE_GEOJSON, None, fetch=boom)
    assert stops == {"type": "FeatureCollection", "features": []}
    assert warning is not None
    assert "504" in warning


def test_overlay_cache_dir_is_sibling_of_tomtom():
    assert overlay_cache_dir(Path("/tmp/cache/tomtom")) == Path("/tmp/cache/overpass")
    assert overlay_cache_dir(None) is None
