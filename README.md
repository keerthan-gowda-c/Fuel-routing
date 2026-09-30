# Fuel Route API

Django 6.1 API: give it a start and finish inside the USA and it returns the driving route, the
cheapest places to fuel up along it (500-mile range), and the total fuel spend at 10 MPG.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py import_stations      # loads data/fuel-prices.csv (~1 s)
python manage.py runserver
python manage.py test                 # 25 tests
```

## Endpoints

| Endpoint | What it does |
|---|---|
| `GET/POST /api/route/` | JSON: route GeoJSON, fuel stops, total cost, `map_url` |
| `GET /map/?start=..&finish=..` | Same plan rendered as a Leaflet map with numbered stops |
| `GET /health/` | liveness |

`start` / `finish` accept `"Chicago, IL"`, a 5-digit ZIP, `"41.88,-87.63"`, or a free-form US address.
Optional: `range_miles` (500), `mpg` (10), `start_fuel_miles` (= range, i.e. full tank), `corridor_miles` (10).

```bash
curl "http://127.0.0.1:8000/api/route/?start=Los%20Angeles,%20CA&finish=New%20York,%20NY"
```

Response (abridged):

```json
{
  "route":  {"distance_miles": 2949.0, "duration_hours": 47.6, "geometry": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [...]}}},
  "fuel_stops": [{"order": 1, "name": "...", "city": "Holbrook", "state": "AZ", "price_per_gallon": 3.139,
                  "route_mile": 539.9, "gallons_purchased": 25.08, "cost": 78.72, "lat": 0, "lon": 0}],
  "summary": {"total_fuel_cost": 717.77, "gallons_purchased": 244.92, "gallons_needed_for_trip": 294.92, "stop_count": 14},
  "meta":   {"external_api_calls": 1, "cached": false, "elapsed_ms": 110.0},
  "map_url": "http://127.0.0.1:8000/map/?start=..."
}
```

Errors are JSON `{"error": "..."}`: 400 bad input / non-US location, 422 no feasible plan (a gap
longer than the range), 502 routing service failure.

## How it works

1. **Locations** - `"City, ST"`, ZIP and lat/lon are resolved locally (bundled ZIP database), so the
   common case makes **zero** geocoding calls. Only free-form addresses hit Nominatim.
2. **Routing** - exactly **one** call to the free public [OSRM](https://project-osrm.org) server
   (`overview=full`, GeoJSON). No API key. Cached by rounded start/finish coordinates, so changing
   `mpg`/`range` re-plans without a new call, and a repeat request makes none.
3. **Stations** - the CSV has no coordinates, so `import_stations` geocodes each stop **once, offline**
   (city centroid from the ZIP database; 6,626/6,626 matched), keeps US rows only, and de-duplicates by
   OPIS id keeping the lowest listed price. Stored in SQLite, held in memory as numpy arrays.
4. **Corridor** - the route is resampled to <=3000 evenly spaced points; a bounding-box prefilter plus a
   vectorised nearest-point search keeps stations within `corridor_miles` and gives each a mile marker.
5. **Optimizer** (`routing/optimizer.py`) - the classic gas-station greedy, which is optimal here: at a stop,
   if a cheaper station (or the destination) is within one tank, buy only enough to reach it; otherwise
   fill up and go to the cheapest station in reach. A test cross-checks it against an exact DP on 400
   random instances.

Typical latency on the real data: ~110 ms for a coast-to-coast trip (excluding the one OSRM round trip),
~4 ms when cached.

## Assumptions - please read

* **Starting tank is full and already paid for**, so `total_fuel_cost` is the fuel *purchased* along the route.
  A trip under 500 miles therefore costs $0. Pass `start_fuel_miles` to change this (e.g. `100`).
  `gallons_needed_for_trip` is reported alongside so the gap is visible.
* **Station coordinates are city-level** (the file only has highway exit text like "I-44, EXIT 283"),
  so a stop can be a few miles from where the pin sits; hence the 10-mile default corridor and the
  `miles_off_route` field. Detour fuel is not modelled.
* The cost-optimal plan buys small top-ups at cheaper stops, so it can make more stops than a
  "fill up every 500 miles" plan. That is the trade for the lowest spend.
* Canadian rows in the CSV (620) are ignored.
* The public OSRM demo server has no uptime guarantee; set `OSRM_BASE_URL` to self-host.

## Layout

```
config/               settings, urls
routing/
  geocoding.py        location parsing + offline city lookup
  osrm.py             the single routing call
  corridor.py         resampling + stations-near-route
  optimizer.py        fuel-stop algorithm
  planner.py          orchestration + caching
  views.py            /api/route/, /map/, /health/
  management/commands/import_stations.py
  tests/              optimizer (incl. exact-DP check), corridor, geocoding, API
data/fuel-prices.csv  the supplied OPIS file
postman/              collection for the demo
```
