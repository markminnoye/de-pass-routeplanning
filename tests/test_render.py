import json

from busroutes.evaluate import evaluate
from busroutes.models import load_scenario
from busroutes.render import compare_markdown, render_map_html, to_geojson
from tests.test_evaluate import SETTINGS


def result_for(school, students, buses, fake_client):
    scenario = load_scenario(
        {
            "name": "r",
            "ordering": "given",
            "buses": [
                {"bus_id": "bus1", "stops": ["s002", "s001"]},
                {"bus_id": "bus2", "stops": ["s004", "s003"]},
            ],
        },
        students,
        buses,
    )
    return evaluate(scenario, school, students, buses, fake_client, SETTINGS)


def test_geojson_has_route_lines_stops_and_school(school, students, buses, fake_client):
    gj = to_geojson(result_for(school, students, buses, fake_client))
    assert gj["type"] == "FeatureCollection"
    kinds = [f["properties"]["kind"] for f in gj["features"]]
    assert kinds.count("route") == 2
    assert kinds.count("stop") == 4
    assert kinds.count("school") == 1
    route = next(f for f in gj["features"] if f["properties"]["kind"] == "route")
    assert route["geometry"]["type"] == "LineString"
    # GeoJSON is [lon, lat]
    assert route["geometry"]["coordinates"][0] == [school.point.lon, school.point.lat]
    stop = next(f for f in gj["features"] if f["properties"]["kind"] == "stop")
    assert {"bus_id", "students", "arrival", "ride_min"} <= set(stop["properties"])
    json.dumps(gj)  # serialisable


def test_map_html_embeds_data_and_leaflet(school, students, buses, fake_client):
    result = result_for(school, students, buses, fake_client)
    html = render_map_html(result, to_geojson(result))
    assert "leaflet" in html.lower()
    assert '"FeatureCollection"' in html
    assert "bus1" in html and "bus2" in html
    assert "max_ride_min" not in html  # metrics rendered as a table, not raw keys
    assert "Langste rit" in html
    assert "L.control.layers" in html
    assert "OV-haltes (De Lijn, TEC, NMBS)" in html
    assert "tile.openstreetmap.de" in html
    assert "World_Street_Map" in html
    assert "tile.openstreetmap.org" not in html
    assert "cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js" in html
    assert ".leaflet-container" in html  # Leaflet CSS inlined (artifact CSP)
    assert "cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/" in html
    assert "unpkg.com" not in html
    assert "leaflet.css" not in html
    assert '<link rel="stylesheet"' not in html


def test_map_html_puts_stop_order_inside_the_marker(school, students, buses, fake_client):
    result = result_for(school, students, buses, fake_client)
    html = render_map_html(result, to_geojson(result))
    assert "L.divIcon" in html
    assert "stop-pin" in html
    assert "stopTextColour" in html
    assert "permanent: true" not in html  # no floating label duplicating the number
    assert "stop-label" not in html


def test_map_html_embeds_transit_stops(school, students, buses, fake_client):
    result = result_for(school, students, buses, fake_client)
    transit = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [4.90, 50.78]},
                "properties": {
                    "kind": "transit",
                    "name": "Tienen Station",
                    "operator_kind": "nmbs",
                    "ref": "8832000",
                    "osm_id": "node/3",
                },
            }
        ],
    }
    html = render_map_html(result, to_geojson(result), transit_geojson=transit)
    assert "Tienen Station" in html
    assert "8832000" in html
    assert "transitLayer" in html
    assert "OV-haltes &copy; OpenStreetMap-bijdragers" in html


def test_compare_markdown_table(school, students, buses, fake_client):
    d = result_for(school, students, buses, fake_client).to_dict()
    md = compare_markdown([d, {**d, "scenario": "other"}])
    assert md.splitlines()[0].startswith("| Scenario")
    assert "| r " in md and "| other " in md
    assert "| Bussen |" in md.splitlines()[0]
    assert "| r | 2 |" in md
