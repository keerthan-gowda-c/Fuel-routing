"""Geometry helpers: even resampling of the route and 'which stations are near it?'."""
import numpy as np

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEG_LAT = 69.055
MILES_PER_DEG_LON_EQ = 69.172
MAX_POINTS = 3000


def _haversine_segments(lon, lat):
    lon, lat = np.radians(lon), np.radians(lat)
    dlat, dlon = np.diff(lat), np.diff(lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def resample_route(coords, total_miles, target_step=0.25, max_points=MAX_POINTS):
    """Interpolate the polyline to evenly spaced points.

    Returns (lat, lon, mile) arrays. `mile` is scaled so it ends exactly at the routing
    engine's driving distance. Points are ~0.25 mi apart on short trips, ~1 mi on cross-country
    ones (capped at 3000), which keeps both the corridor search and the JSON payload small.
    """
    lon, lat = coords[:, 0], coords[:, 1]
    cum = np.concatenate([[0.0], np.cumsum(_haversine_segments(lon, lat))])
    if cum[-1] <= 0:
        return lat[:1].repeat(2), lon[:1].repeat(2), np.array([0.0, 0.0])
    cum *= total_miles / cum[-1]
    n = int(np.clip(np.ceil(total_miles / target_step) + 1, 2, max_points))
    miles = np.linspace(0.0, total_miles, n)
    return np.interp(miles, cum, lat), np.interp(miles, cum, lon), miles


def stations_near_route(st_lat, st_lon, route_lat, route_lon, route_mile, corridor_miles, chunk=400):
    """For each station within `corridor_miles` of the route return (index, mile_marker, off_route_miles)."""
    lat_pad = corridor_miles / MILES_PER_DEG_LAT
    lon_pad = corridor_miles / (MILES_PER_DEG_LON_EQ * max(np.cos(np.radians(np.abs(route_lat).max())), 0.2))
    box = (
        (st_lat >= route_lat.min() - lat_pad)
        & (st_lat <= route_lat.max() + lat_pad)
        & (st_lon >= route_lon.min() - lon_pad)
        & (st_lon <= route_lon.max() + lon_pad)
    )
    cand = np.flatnonzero(box)
    out_idx, out_mile, out_off = [], [], []
    for s in range(0, len(cand), chunk):
        ids = cand[s : s + chunk]
        dy = (st_lat[ids, None] - route_lat[None, :]) * MILES_PER_DEG_LAT
        dx = (st_lon[ids, None] - route_lon[None, :]) * MILES_PER_DEG_LON_EQ * np.cos(np.radians(st_lat[ids, None]))
        d2 = dx * dx + dy * dy
        nearest = d2.argmin(axis=1)
        dist = np.sqrt(d2[np.arange(len(ids)), nearest])
        ok = dist <= corridor_miles
        out_idx.append(ids[ok])
        out_mile.append(route_mile[nearest[ok]])
        out_off.append(dist[ok])
    if not out_idx:
        return np.array([], int), np.array([]), np.array([])
    return np.concatenate(out_idx), np.concatenate(out_mile), np.concatenate(out_off)
