"""Output: GeoJSON, a self-contained Leaflet map per scenario, and comparison tables.

The map uses OpenStreetMap.de tiles plus an overlay of De Lijn / TEC / NMBS
stops fetched via Overpass. tile.openstreetmap.org is not used: a local
file:// map.html sends no Referer, and OSMF volunteer tiles then return 403.
Leaflet CSS is inlined (a published artifact blocks external stylesheets) and
its images are data URIs. Leaflet JS comes from cdnjs, which that artifact
still allows. A published artifact blocks every external image, so the tiles
for the scenario bbox are embedded as data URIs; other zoom levels fall back
to the live OSM.de URL, which a normal browser can load.
"""

from __future__ import annotations

import html
import json

from busroutes.evaluate import ScenarioResult
from busroutes.leaflet_css import LEAFLET_CSS

BUS_COLOURS = ["#d7263d", "#1b7f79", "#f46036", "#2e294e", "#3a86ff", "#8338ec", "#ffbe0b"]

COMPARE_COLUMNS = [
    ("scenario", "Scenario"),
    ("mode", "Modus"),
    ("buses_used", "Bussen"),
    ("max_ride_min", "Langste rit (min)"),
    ("avg_ride_min", "Gem. rit (min)"),
    ("median_ride_min", "Mediaan rit (min)"),
    ("rides_over_60_min", "Ritten > 60 min"),
    ("max_to_stop_km", "Max. thuis→stop (km)"),
    ("total_drive_min", "Totale rijtijd (min)"),
    ("total_km", "Km"),
    ("avg_occupancy_pct", "Bezetting (%)"),
    ("earliest_departure", "Vroegste vertrek"),
    ("arrival", "Aankomst"),
]


def _colour(i: int) -> str:
    return BUS_COLOURS[i % len(BUS_COLOURS)]


def to_geojson(result: ScenarioResult) -> dict:
    features: list[dict] = []
    for i, bus in enumerate(result.buses):
        if not bus.stops:
            continue
        coords: list[list[float]] = []
        for leg in bus.route.legs:
            for p in leg.points:
                pair = [p.lon, p.lat]
                if not coords or coords[-1] != pair:
                    coords.append(pair)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "kind": "route",
                    "bus_id": bus.bus.id,
                    "colour": _colour(i),
                    "students": bus.student_count,
                    "capacity": bus.bus.capacity,
                    "departure": bus.departure.strftime("%H:%M"),
                    "arrival": bus.arrival.strftime("%H:%M"),
                    "drive_min": round(bus.drive_s / 60, 1),
                    "km": round(bus.length_m / 1000, 1),
                },
            }
        )
        for order, s in enumerate(bus.stops, start=1):
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [s.stop.point.lon, s.stop.point.lat],
                    },
                    "properties": {
                        "kind": "stop",
                        "id": s.stop.id,
                        "name": s.stop.name,
                        "bus_id": bus.bus.id,
                        "colour": _colour(i),
                        "order": order,
                        "students": list(s.stop.students),
                        "arrival": s.arrival.strftime("%H:%M"),
                        "ride_min": round(s.ride_s / 60, 1),
                    },
                }
            )
    features.append(
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [result.school.point.lon, result.school.point.lat],
            },
            "properties": {
                "kind": "school",
                "name": result.school.name,
                "arrival": result.school.target_arrival.strftime("%H:%M"),
            },
        }
    )
    return {"type": "FeatureCollection", "features": features}


def _compare_cell(m: dict, key: str) -> str:
    if key == "scenario":
        return str(m[key])
    if key == "mode":
        return str(m.get("settings", {}).get("mode", "tomtom"))
    return str(m["summary"].get(key, ""))


def compare_markdown(metrics: list[dict]) -> str:
    header = "| " + " | ".join(label for _, label in COMPARE_COLUMNS) + " |"
    sep = "|" + "|".join("---" for _ in COMPARE_COLUMNS) + "|"
    rows = []
    for m in metrics:
        cells = [_compare_cell(m, key) for key, _ in COMPARE_COLUMNS]
        rows.append("| " + " | ".join(cells) + " |")
    text = "\n".join([header, sep, *rows]) + "\n"
    modes = {m.get("settings", {}).get("mode", "tomtom") for m in metrics}
    if "offline" in modes and "tomtom" in modes:
        text += (
            "\nLet op: de tabel mengt offline- en tomtom-modi; "
            "cijfers zijn niet 1-op-1 vergelijkbaar.\n"
        )
    return text


def _summary_rows(d: dict) -> str:
    s = d["summary"]
    km = f"{s['total_km']} km"
    if d.get("settings", {}).get("km_estimated"):
        km += " (geschat)"
    items = [
        ("Leerlingen", s["students"]),
        ("Langste rit", f"{s['max_ride_min']} min"),
        ("Gemiddelde rit", f"{s['avg_ride_min']} min"),
        ("Mediaan rit", f"{s['median_ride_min']} min"),
        ("Totale rijtijd", f"{s['total_drive_min']} min"),
        ("Totale afstand", km),
        ("Gem. bezetting", f"{s['avg_occupancy_pct']} %"),
        ("Vroegste vertrek", s["earliest_departure"]),
        ("Aankomst school", s["arrival"]),
    ]
    return "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in items
    )


def _bus_rows(d: dict, colours: dict[str, str]) -> str:
    rows = []
    for b in d["buses"]:
        bus_id = html.escape(b["bus_id"])
        swatch = f'<span class="sw" style="background:{colours.get(b["bus_id"], "#999")}"></span>'
        toggle = (
            '<label class="bus">'
            f'<input type="checkbox" class="bus-toggle" data-bus="{bus_id}" checked>'
            f"{swatch}{bus_id}</label>"
        )
        rows.append(
            "<tr>"
            f"<td>{toggle}</td>"
            f"<td>{b['students']}/{b['capacity']}</td>"
            f"<td>{html.escape(b['departure'])}</td>"
            f"<td>{b['drive_min']}</td>"
            f"<td>{b['km']}</td>"
            f"<td>{b['max_ride_min']}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_map_html(
    result: ScenarioResult,
    geojson: dict,
    transit_geojson: dict | None = None,
    basemap_tiles: dict[str, str] | None = None,
) -> str:
    d = result.to_dict()
    colours = {
        f["properties"]["bus_id"]: f["properties"]["colour"]
        for f in geojson["features"]
        if f["properties"]["kind"] == "route"
    }
    title = html.escape(f"Scenario {d['scenario']}")
    description = html.escape(d.get("description", ""))
    banner = ""
    if d.get("settings", {}).get("mode") == "offline":
        banner = '<p class="banner">Offline-schatting: tijden uit de matrix, rechte lijnen, km geschat</p>'
    data = json.dumps(geojson).replace("</", "<\\/")
    transit = json.dumps(transit_geojson or {"type": "FeatureCollection", "features": []}).replace(
        "</", "<\\/"
    )
    tiles = json.dumps(basemap_tiles or {}).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
{LEAFLET_CSS}
  html, body {{ margin: 0; height: 100%; font: 14px/1.4 system-ui, sans-serif; }}
  #wrap {{ display: flex; height: 100%; min-height: 100vh; }}
  #panel {{ width: 360px; overflow: auto; padding: 16px; box-sizing: border-box; border-right: 1px solid #ddd; }}
  #map {{ flex: 1; min-height: 420px; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }}
  p.desc {{ color: #555; margin: 0 0 12px; }}
  p.banner {{ background: #fff3cd; border: 1px solid #ffc107; padding: 8px 12px; margin: 0 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
  th, td {{ text-align: left; padding: 3px 6px; border-bottom: 1px solid #eee; vertical-align: top; }}
  th {{ font-weight: 600; color: #333; }}
  .sw {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; }}
  label.bus {{ display: inline-flex; align-items: center; cursor: pointer; }}
  .bus-toggle {{ margin: 0 6px 0 0; }}
  tr.off {{ opacity: 0.45; }}
  .stop-pin {{ background: none; border: 0; }}
  .stop-pin span {{ display: flex; align-items: center; justify-content: center; box-sizing: border-box; width: 22px; height: 22px; border: 2px solid #fff; border-radius: 50%; box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35); font-size: 11px; font-weight: 700; }}
  @media (max-width: 800px) {{ #wrap {{ flex-direction: column; }} #panel {{ width: auto; border-right: 0; border-bottom: 1px solid #ddd; max-height: 45%; }} }}
</style>
</head>
<body>
<div id="wrap">
  <div id="panel">
    <h1>{title}</h1>
    <p class="desc">{description}</p>
    {banner}
    <table>{_summary_rows(d)}</table>
    <table>
      <thead><tr><th>Bus</th><th>Bezet</th><th>Vertrek</th><th>Rijtijd</th><th>Km</th><th>Langste rit</th></tr></thead>
      <tbody>{_bus_rows(d, colours)}</tbody>
    </table>
    <p class="desc">Tijden voor verkeer op {html.escape(d["settings"]["depart_at_reference"])} ({html.escape(d["settings"]["traffic"])}).</p>
  </div>
  <div id="map"></div>
</div>
<script>
const data = {data};
const transitData = {transit};
const embeddedTiles = {tiles};
const map = L.map('map');
const osmAttr = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
function osmTileUrl(z, x, y) {{
  return 'https://tile.openstreetmap.de/' + z + '/' + x + '/' + y + '.png';
}}
const OsmTiles = L.GridLayer.extend({{
  createTile: function (coords) {{
    const img = document.createElement('img');
    const key = coords.z + '/' + coords.x + '/' + coords.y;
    img.alt = '';
    img.src = embeddedTiles[key] || osmTileUrl(coords.z, coords.x, coords.y);
    return img;
  }}
}});
const osmDe = new OsmTiles({{ maxZoom: 18, attribution: osmAttr }});
const esri = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  maxZoom: 19,
  attribution: 'Tiles &copy; Esri'
}});
osmDe.addTo(map);
// Dark digits on light bus colours, white on dark ones (perceived brightness).
const stopTextColour = hex => {{
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return (r * 299 + g * 587 + b * 114) / 1000 > 150 ? '#1a1a1a' : '#fff';
}};
const layer = L.geoJSON(data, {{
  style: f => ({{ color: f.properties.colour, weight: 4, opacity: 0.85 }}),
  pointToLayer: (f, latlng) => {{
    const p = f.properties;
    if (p.kind === 'school') {{
      return L.circleMarker(latlng, {{ radius: 10, color: '#000', fillColor: '#fff', fillOpacity: 1, weight: 3 }});
    }}
    if (p.kind === 'stop') {{
      return L.marker(latlng, {{
        icon: L.divIcon({{
          className: 'stop-pin',
          html: `<span style="background:${{p.colour}};color:${{stopTextColour(p.colour)}}">${{p.order}}</span>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
          popupAnchor: [0, -12]
        }})
      }});
    }}
    return L.circleMarker(latlng, {{ radius: 6, color: '#fff', fillColor: p.colour, fillOpacity: 1, weight: 1.5 }});
  }},
  onEachFeature: (f, l) => {{
    const p = f.properties;
    if (p.kind === 'route') {{
      l.bindPopup(`<b>${{p.bus_id}}</b><br>${{p.students}}/${{p.capacity}} leerlingen<br>vertrek ${{p.departure}} → aankomst ${{p.arrival}}<br>${{p.drive_min}} min, ${{p.km}} km`);
    }} else if (p.kind === 'stop') {{
      const who = p.students.length === 1 ? p.students[0] : p.students.length + ' leerlingen';
      l.bindPopup(`<b>${{p.name || p.id}}</b> (${{p.bus_id}}, stop ${{p.order}})<br>${{who}}<br>ophalen ${{p.arrival}}, rit ${{p.ride_min}} min`);
    }} else {{
      l.bindPopup(`<b>${{p.name}}</b><br>aankomst ${{p.arrival}}`);
    }}
  }}
}}).addTo(map);
const transitColours = {{ delijn: '#ffdd00', tec: '#e30613', nmbs: '#003d6b' }};
const transitLabels = {{ delijn: 'De Lijn', tec: 'TEC', nmbs: 'NMBS' }};
const transitLayer = L.geoJSON(transitData, {{
  attribution: 'OV-haltes &copy; OpenStreetMap-bijdragers',
  pointToLayer: (f, latlng) => {{
    const p = f.properties;
    return L.circleMarker(latlng, {{
      radius: 4, color: '#fff', fillColor: transitColours[p.operator_kind] || '#666',
      fillOpacity: 0.9, weight: 1
    }});
  }},
  onEachFeature: (f, l) => {{
    const p = f.properties;
    const op = transitLabels[p.operator_kind] || p.operator_kind;
    const ref = p.ref ? ' · ' + p.ref : '';
    l.bindPopup(`<b>${{p.name}}</b><br>${{op}}${{ref}}`);
  }}
}}).addTo(map);
L.control.layers({{
  'OpenStreetMap': osmDe,
  'Esri straten': esri
}}, {{
  'Schoolbusroutes': layer,
  'OV-haltes (De Lijn, TEC, NMBS)': transitLayer
}}).addTo(map);
const fit = () => {{
  map.invalidateSize();
  if (layer.getBounds().isValid()) map.fitBounds(layer.getBounds().pad(0.05));
}};
fit();
// A published artifact gives the map pane its height late, and blocks every
// external image. Snap to an embedded zoom only when a live tile is refused,
// so a normal browser keeps the fitBounds zoom and can still load other levels.
const snapToEmbedded = () => {{
  const zooms = Object.keys(embeddedTiles).map(key => +key.split('/')[0]);
  if (!zooms.length) return;
  const current = map.getZoom();
  let target = zooms[0];
  zooms.forEach(zoom => {{
    if (Math.abs(zoom - current) < Math.abs(target - current)) target = zoom;
  }});
  if (target !== current) map.setZoom(target);
}};
requestAnimationFrame(() => {{
  const size = map.getSize();
  if (size.x < 20 || size.y < 20) fit();
  const keys = Object.keys(embeddedTiles);
  if (!keys.length) return;
  const probe = new Image();
  probe.onerror = () => snapToEmbedded();
  probe.src = osmTileUrl.apply(null, keys[0].split('/'));
}});
window.addEventListener('resize', () => map.invalidateSize());
// The legend doubles as an on/off switch per bus (route line plus its stops).
const busLayers = {{}};
layer.eachLayer(l => {{
  const id = l.feature && l.feature.properties.bus_id;
  if (id) {{
    (busLayers[id] = busLayers[id] || []).push(l);
  }}
}});
document.querySelectorAll('.bus-toggle').forEach(box => {{
  box.addEventListener('change', () => {{
    (busLayers[box.dataset.bus] || []).forEach(l => {{
      if (box.checked) {{
        layer.addLayer(l);
      }} else {{
        layer.removeLayer(l);
      }}
    }});
    box.closest('tr').classList.toggle('off', !box.checked);
  }});
}});
</script>
</body>
</html>
"""
