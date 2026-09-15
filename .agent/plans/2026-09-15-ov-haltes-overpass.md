# 2026-09-15 — OV-haltes via Overpass overlay

Status: ✅ klaar

**Doel:** publieke De Lijn-, TEC- en NMBS-haltes tonen op de bestaande Leaflet + OSM-kaart, uitzetbaar via layer control. Thunderforest-basemap is bewust niet gekozen (API-key in tile-URL).

**Aanpak:** Overpass API + disk-cache (`.cache/overpass/`). Soft-fail als Overpass down is. Plugin-sync via `scripts/build_plugin.py`.

Zie implementatie in `busroutes/overpass.py`, `busroutes/render.py`, `busroutes/cli.py`.
