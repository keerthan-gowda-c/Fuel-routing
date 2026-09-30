"""Turn user input into (lat, lon) inside the USA.

Accepted formats (first match wins, network is only touched by the last one):
  * "lat,lon"            e.g. "41.8781,-87.6298"
  * 5-digit ZIP          e.g. "60601"
  * "City, ST"           e.g. "Chicago, IL"  (local ZIP database, no network)
  * anything else        free-form address -> Nominatim (1 HTTP call, US only)
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import requests
import zipcodes
from django.conf import settings
from django.core.cache import cache

from .errors import LocationError

_LATLON = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_ZIP = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")
_CITY_ST = re.compile(r"^\s*(?P<city>[^,]+?)\s*,\s*(?P<state>[A-Za-z]{2})\s*(?:,?\s*(?:USA|US))?\s*$", re.I)
_ABBREV = {"MT": "MOUNT", "FT": "FORT", "ST": "SAINT", "STE": "SAINTE", "N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}

# Rough bounding boxes: contiguous US, Alaska, Hawaii.
_US_BOXES = [(24.0, 49.6, -125.5, -66.5), (51.0, 71.6, -179.9, -129.0), (18.5, 22.5, -160.7, -154.5)]


@dataclass
class Location:
    query: str
    lat: float
    lon: float
    label: str
    source: str  # "coordinates" | "zip" | "city" | "nominatim"


class ApiCalls:
    """Counts calls to external services made while serving one request."""

    def __init__(self):
        self.count = 0

    def hit(self):
        self.count += 1


def in_usa(lat, lon):
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in _US_BOXES)


def city_key(city):
    tokens = re.sub(r"[^A-Z0-9 ]", " ", city.upper()).split()
    return "".join(_ABBREV.get(t, t) for t in tokens)


@lru_cache(maxsize=1)
def city_centroids():
    """{(state, city_key): (lat, lon)} built once from the bundled ZIP database (offline)."""
    buckets = defaultdict(list)
    for z in zipcodes.list_all():
        if not z.get("lat") or not z.get("long") or z.get("zip_code_type") == "MILITARY":
            continue
        point = (float(z["lat"]), float(z["long"]))
        for name in [z["city"], *(z.get("acceptable_cities") or [])]:
            buckets[(z["state"], city_key(name))].append(point)
    return {k: tuple(np.mean(v, axis=0)) for k, v in buckets.items()}


def lookup_city(city, state):
    return city_centroids().get((state.upper().strip(), city_key(city)))


def _nominatim(query, calls):
    key = "geo:" + query.lower().strip()
    hit = cache.get(key)
    if hit:
        return hit
    calls.hit()
    try:
        resp = requests.get(
            settings.NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        rows = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise LocationError(f"Could not geocode '{query}': {exc}") from exc
    if not rows:
        raise LocationError(f"Could not find a US location for '{query}'.")
    out = (float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name", query))
    cache.set(key, out, settings.CACHE_TTL_SECONDS)
    return out


def resolve_location(text, calls=None):
    calls = calls or ApiCalls()
    if not isinstance(text, str) or not text.strip():
        raise LocationError("Location is required.")
    text = text.strip()

    if m := _LATLON.match(text):
        lat, lon = float(m.group(1)), float(m.group(2))
        loc = Location(text, lat, lon, f"{lat:.5f}, {lon:.5f}", "coordinates")
    elif m := _ZIP.match(text):
        rows = zipcodes.matching(m.group(1))
        if not rows or not rows[0].get("lat"):
            raise LocationError(f"Unknown ZIP code '{m.group(1)}'.")
        z = rows[0]
        loc = Location(text, float(z["lat"]), float(z["long"]), f"{z['city']}, {z['state']} {z['zip_code']}", "zip")
    elif (m := _CITY_ST.match(text)) and (pt := lookup_city(m.group("city"), m.group("state"))):
        loc = Location(text, pt[0], pt[1], f"{m.group('city').title()}, {m.group('state').upper()}", "city")
    else:
        lat, lon, label = _nominatim(text, calls)
        loc = Location(text, lat, lon, label, "nominatim")

    if not in_usa(loc.lat, loc.lon):
        raise LocationError(f"'{text}' resolves outside the USA ({loc.lat:.4f}, {loc.lon:.4f}).")
    return loc
