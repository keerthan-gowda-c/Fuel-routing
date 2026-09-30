import hashlib
import time
import numpy as np
from django.conf import settings
from django.core.cache import cache
from .corridor import resample_route, stations_near_route
from .geocoding import ApiCalls, resolve_location
from .optimizer import plan_fuel_stops
from .osrm import fetch_route
from .stations import get_index


def _key(prefix, *parts):
    return prefix + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()

def _route_for(start, finish, calls):
    """OSRM result cached by (rounded) coordinates so repeat / re-parameterised requests skip the network."""
    key = _key("route:", round(start.lat, 3), round(start.lon, 3), round(finish.lat, 3), round(finish.lon, 3))
    route = cache.get(key)
    if route is None:
        route = fetch_route(start, finish, calls)
        cache.set(key, route, settings.CACHE_TTL_SECONDS)
    return route

def plan_trip(start_text, finish_text, range_miles=None, mpg=None, start_fuel_miles=None, corridor_miles=None):
    t0 = time.perf_counter()
    range_miles = range_miles or settings.DEFAULT_RANGE_MILES
    mpg = mpg or settings.DEFAULT_MPG
    corridor_miles = corridor_miles or settings.DEFAULT_CORRIDOR_MILES
    start_fuel = range_miles if start_fuel_miles is None else start_fuel_miles
    calls = ApiCalls()
    start = resolve_location(start_text, calls)
    finish = resolve_location(finish_text, calls)

    plan_key = _key("plan:", round(start.lat, 3), round(start.lon, 3), round(finish.lat, 3),
                    round(finish.lon, 3), range_miles, mpg, start_fuel, corridor_miles)
    cached = cache.get(plan_key)
    if cached:
        cached = dict(cached, meta={**cached["meta"], "cached": True, "external_api_calls": calls.count,
                                    "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)})
        cached["start"], cached["finish"] = _loc(start), _loc(finish)
        return cached

    route = _route_for(start, finish, calls)
    r_lat, r_lon, r_mile = resample_route(route.coords, route.distance_miles)

    idx = get_index()
    ids, miles, off = stations_near_route(idx.lat, idx.lon, r_lat, r_lon, r_mile, corridor_miles)
    plan = plan_fuel_stops(miles.tolist(), idx.price[ids].tolist(), route.distance_miles,
                           range_miles=range_miles, mpg=mpg, start_fuel_miles=start_fuel)

    stops = []
    for n, s in enumerate(plan.stops, 1):
        row = idx.rows[int(ids[s.station])]
        stops.append({
            "order": n,
            "opis_id": row["opis_id"],
            "name": row["name"],
            "address": row["address"],
            "city": row["city"],
            "state": row["state"],
            "lat": row["lat"],
            "lon": row["lon"],
            "price_per_gallon": round(s.price, 4),
            "route_mile": round(s.mile, 1),
            "miles_off_route": round(float(off[s.station]), 1),
            "tank_on_arrival_gallons": round(s.tank_on_arrival_miles / mpg, 2),
            "gallons_purchased": round(s.gallons, 2),
            "cost": round(s.cost, 2),
        })

    result = {
        "start": _loc(start),
        "finish": _loc(finish),
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_hours, 2),
            "geometry": {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString",
                             "coordinates": np.round(np.column_stack([r_lon, r_lat]), 5).tolist()},
            },
        },
        "fuel_stops": stops,
        "summary": {
            "total_fuel_cost": round(plan.total_cost, 2),
            "gallons_purchased": round(plan.total_gallons, 2),
            "gallons_needed_for_trip": round(route.distance_miles / mpg, 2),
            "stop_count": len(stops),
            "vehicle": {"range_miles": range_miles, "mpg": mpg, "start_fuel_miles": start_fuel},
            "assumptions": [
                "Total cost is fuel PURCHASED along the route; the starting tank is treated as already paid for.",
                "Each purchase is sized to reach the next cheaper stop (or the destination) - no wasted fuel.",
                f"Stations are those within {corridor_miles:g} miles of the route (station coordinates are city-level).",
                "Price per station is the lowest price listed for that OPIS id.",
            ],
        },
        "meta": {"cached": False},
    }
    result["meta"].update(external_api_calls=calls.count, elapsed_ms=round((time.perf_counter() - t0) * 1000, 1))
    cache.set(plan_key, result, settings.CACHE_TTL_SECONDS)
    return result

def _loc(loc):
    return {"query": loc.query, "label": loc.label, "lat": round(loc.lat, 5), "lon": round(loc.lon, 5)}
