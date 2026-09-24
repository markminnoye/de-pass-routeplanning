import json

from busroutes.evaluate import evaluate
from busroutes.models import load_scenario
from busroutes.offline import OfflineClient
from busroutes.render import compare_markdown, render_map_html, to_geojson
from busroutes.tomtom import _point_key
from tests.test_evaluate import SETTINGS
from tests.test_offline import write_origin_row


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
    # Open morning route: first stop, then the school. GeoJSON is [lon, lat].
    first = result_for(school, students, buses, fake_client).buses[0].stops[0].stop.point
    assert route["geometry"]["coordinates"][0] == [first.lon, first.lat]
    assert route["geometry"]["coordinates"][-1] == [school.point.lon, school.point.lat]
    assert route["properties"]["direction"] == "naar school"
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
    assert "cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/" not in html
    assert "embeddedTiles" in html
    assert "unpkg.com" not in html
    assert "leaflet.css" not in html
    assert '<link rel="stylesheet"' not in html


def test_map_html_embeds_basemap_tiles_as_data_uris(school, students, buses, fake_client):
    result = result_for(school, students, buses, fake_client)
    tiles = {"12/2102/1374": "data:image/png;base64,AAAA"}
    html = render_map_html(result, to_geojson(result), basemap_tiles=tiles)
    assert '"12/2102/1374": "data:image/png;base64,AAAA"' in html
    assert "embeddedTiles[key] || osmTileUrl" in html
    assert "probe.onerror = () => snapToEmbedded()" in html


def test_map_html_puts_stop_order_inside_the_marker(school, students, buses, fake_client):
    result = result_for(school, students, buses, fake_client)
    html = render_map_html(result, to_geojson(result))
    assert "L.divIcon" in html
    assert "stop-pin" in html
    assert "stopTextColour" in html
    assert "permanent: true" not in html  # no floating label duplicating the number
    assert "stop-label" not in html


def test_map_html_legend_toggles_buses(school, students, buses, fake_client):
    result = result_for(school, students, buses, fake_client)
    html = render_map_html(result, to_geojson(result))
    assert 'class="bus-toggle" data-bus="bus1" checked' in html
    assert 'class="bus-toggle" data-bus="bus2" checked' in html
    assert "border-radius: 50%" in html  # round legend swatches, not squares
    assert "layer.removeLayer(l)" in html


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


def test_map_html_offline_banner(tmp_path, school, students, buses):
    one = {"s001": students["s001"]}
    one_bus = {"bus1": buses["bus1"]}
    scenario = load_scenario(
        {"name": "off", "ordering": "given", "buses": [{"bus_id": "bus1", "stops": ["s001"]}]},
        one,
        one_bus,
    )
    school_pt, student_pt = school.point, one["s001"].point
    write_origin_row(tmp_path, school_pt, {_point_key(student_pt): 400})
    write_origin_row(tmp_path, student_pt, {_point_key(school_pt): 500})
    result = evaluate(scenario, school, one, one_bus, OfflineClient(tmp_path), SETTINGS)
    html = render_map_html(result, to_geojson(result))
    assert "Offline-schatting: tijden uit de matrix, rechte lijnen, km geschat" in html
    assert "(geschat)" in html


def test_compare_markdown_table(school, students, buses, fake_client):
    d = result_for(school, students, buses, fake_client).to_dict()
    md = compare_markdown([d, {**d, "scenario": "other"}])
    assert md.splitlines()[0].startswith("| Scenario")
    assert "| r " in md and "| other " in md
    assert "| Bussen |" in md.splitlines()[0]
    assert "| r | tomtom | naar school | 2 |" in md


def test_compare_markdown_includes_modus_column(school, students, buses, fake_client):
    d = result_for(school, students, buses, fake_client).to_dict()
    md = compare_markdown([d])
    header = md.splitlines()[0]
    assert "| Modus |" in header
    assert "| Richting |" in header
    assert "| tomtom |" in md
    assert "| naar school |" in md


def test_compare_markdown_marks_mixed_modes(school, students, buses, fake_client):
    d = result_for(school, students, buses, fake_client).to_dict()
    offline = {
        **d,
        "scenario": "off",
        "settings": {**d["settings"], "mode": "offline", "km_estimated": True},
    }
    md = compare_markdown([d, offline])
    assert "| tomtom |" in md
    assert "| offline |" in md
    assert "niet 1-op-1 vergelijkbaar" in md
