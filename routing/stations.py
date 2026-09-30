"""In-memory numpy view of the Station table (loaded once per process, ~6.6k rows)."""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .models import Station


@dataclass
class StationIndex:
    lat: np.ndarray
    lon: np.ndarray
    price: np.ndarray
    rows: list  # parallel list of dicts with the display fields


@lru_cache(maxsize=1)
def get_index():
    qs = list(Station.objects.values("opis_id", "name", "address", "city", "state", "price", "lat", "lon"))
    return StationIndex(
        lat=np.array([r["lat"] for r in qs], dtype=float),
        lon=np.array([r["lon"] for r in qs], dtype=float),
        price=np.array([float(r["price"]) for r in qs], dtype=float),
        rows=qs,
    )


def reset_index():
    get_index.cache_clear()
