import numpy as np
from django.core.cache import cache
from django.test import TestCase
from unittest import mock

from routing.models import Station
from routing.osrm import RouteData
from routing.stations import reset_index

# ~1,000-mile due-east line at 40N (Nebraska-ish to Ohio-ish), like a long interstate.
LONS = np.linspace(-102.0, -84.0, 200)
COORDS = np.column_stack([LONS, np.full_like(LONS, 40.0)])
ROUTE = RouteData(coords=COORDS, distance_miles=950.0, duration_hours=14.5)


def station(oid, lon, price, lat=40.0):
    return Station(opis_id=oid, name=f"STOP {oid}", address="I-80, EXIT 1", city="Testville", state="NE",
                   price=price, lat=lat, lon=lon)


class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        Station.objects.bulk_create([
            station(1, -99.0, "3.900"),    # ~ mile 160, pricey
            station(2, -95.0, "3.200"),    # ~ mile 480, cheap
            station(3, -91.0, "3.600"),    # ~ mile 805
            station(4, -95.0, "2.000", lat=41.5),   # cheapest, but ~100 mi off the route -> ignored
        ])
        reset_index()
        self.addCleanup(reset_index)
        patcher = mock.patch("routing.planner.fetch_route", side_effect=lambda s, f, calls: (calls.hit(), ROUTE)[1])
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, **extra):
        params = {"start": "41.0,-102.0", "finish": "40.0,-84.0", **extra}
        return self.client.get("/api/route/", params)

    def test_returns_route_stops_and_total_cost(self):
        body = self.get().json()
        self.assertEqual(body["route"]["geometry"]["geometry"]["type"], "LineString")
        self.assertEqual(body["route"]["distance_miles"], 950.0)
        stops = body["fuel_stops"]
        self.assertEqual([s["opis_id"] for s in stops], [2, 3])  # skips the pricey 1st stop and the off-route one
        self.assertAlmostEqual(body["summary"]["total_fuel_cost"], sum(s["cost"] for s in stops), places=1)
        self.assertTrue(body["map_url"].startswith("http"))

    def test_single_routing_call_and_second_request_is_cached(self):
        first = self.get().json()
        self.assertEqual(first["meta"]["external_api_calls"], 1)
        second = self.get().json()
        self.assertTrue(second["meta"]["cached"])
        self.assertEqual(second["meta"]["external_api_calls"], 0)
        self.assertEqual(self.fetch.call_count, 1)

    def test_changing_vehicle_params_reuses_cached_route(self):
        self.get()
        self.get(mpg=8)
        self.assertEqual(self.fetch.call_count, 1)

    def test_post_json(self):
        r = self.client.post("/api/route/", {"start": "41.0,-102.0", "finish": "40.0,-84.0"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_validation_errors(self):
        self.assertEqual(self.client.get("/api/route/", {"start": "Chicago, IL"}).status_code, 400)
        self.assertEqual(self.get(mpg="abc").status_code, 400)
        self.assertEqual(self.get(range_miles="10").status_code, 400)
        self.assertEqual(self.client.get("/api/route/", {"start": "51.5,-0.12", "finish": "40.0,-84.0"}).status_code, 400)

    def test_infeasible_when_gap_exceeds_range(self):
        Station.objects.filter(opis_id__in=[2, 3]).delete()
        reset_index()
        r = self.get()
        self.assertEqual(r.status_code, 422)
        self.assertIn("error", r.json())

    def test_map_page_renders(self):
        r = self.client.get("/map/", {"start": "41.0,-102.0", "finish": "40.0,-84.0"})
        self.assertContains(r, "leaflet")
        self.assertContains(r, "STOP 2")
