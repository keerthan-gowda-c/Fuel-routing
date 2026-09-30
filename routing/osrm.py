from dataclasses import dataclass
import numpy as np
import requests
from django.conf import settings
from .errors import RoutingError

METERS_PER_MILE = 1609.344

@dataclass
class RouteData:
    coords: np.ndarray  # (N, 2) array of [lon, lat]
    distance_miles: float
    duration_hours: float

def fetch_route(start, finish, calls):
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{start.lon:.6f},{start.lat:.6f};{finish.lon:.6f},{finish.lat:.6f}"
    calls.hit()
    try:
        resp = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false", "alternatives": "false"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No drivable route found ({data.get('code', 'unknown error')}: {data.get('message', '')}).")
    route = data["routes"][0]
    return RouteData(
        coords=np.asarray(route["geometry"]["coordinates"], dtype=float),
        distance_miles=route["distance"] / METERS_PER_MILE,
        duration_hours=route["duration"] / 3600.0,
    )
