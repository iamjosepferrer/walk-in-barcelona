# Walk in Barcelona

Pick any two places in Barcelona and see how the streets change along the shortest walk between them. Built only from open data.

The page finds the shortest way on foot between two points and draws nine street conditions along it: slope, crossings, parks, trees, air quality, shade and water, shops and terraces, traffic and pedestrian streets. Every one of the city's 14,816 street sections is ranked against the rest, so a typical Barcelona street sits in the middle.

## Run it

Run `python scripts/07_build.py` (no dependencies), then open `dist/index.html` in a browser or serve `dist/` as static files. No server code, no API keys: the street graph and the search index ship as two JavaScript files.

## Rebuild the data

```
pip install -r requirements.txt
python scripts/01_fetch.py        # 11 Open Data BCN datasets into data/raw/
python scripts/02_graph.py        # street graph from the city's street sections
python scripts/03_elevation.py    # ICGC terrain model 2 m (about 12 minutes, resumable)
python scripts/04_indicators.py   # nine conditions per street section
python scripts/05_export.py       # web/data.js
python scripts/06_places.py       # web/places.js: landmarks, neighbourhoods, street corners
python scripts/07_build.py        # dist/
```

`config/landmarks.json` lists the named places offered in the search boxes. The page uses the Josep Ferrer Dataviz style kit in `web/jf-dataviz/`.

## Method and data

The street conditions follow the walkability indicators of Transform Transport, [UX Mobility: Multi-User Walkability Route Planner](https://transformtransport.org/research/inclusive-mobility/ux-mobility-multi-user-walkability-route-planner/) (Milan, 2025), built on the Walk21 framework. The study's other three indicators (sidewalk width, pavement, lighting) have no city-wide open data for Barcelona and are left out. Three conditions are proxies: shade and water (tree canopy, climate shelters, fountains), low traffic (2017 road noise map) and pedestrian streets (plazas and sections without traffic noise).

Data: Open Data BCN (street sections and 2017 noise map, 2024 NO2 map, crossings, Biodiversity Atlas trees, park trees, climate shelters, fountains, benches, escalators, ground-floor premises, terraces), CC BY 4.0. Elevation: ICGC terrain model 2 m, CC BY 4.0.

By Josep Ferrer, [databites](https://projects.databites.tech).
