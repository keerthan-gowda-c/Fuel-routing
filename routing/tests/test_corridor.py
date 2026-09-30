import numpy as np
from django.test import SimpleTestCase

from routing.corridor import resample_route, stations_near_route


class CorridorTests(SimpleTestCase):
    def setUp(self):
        # Due-east line at 40N from -100 to -90 (~530 miles).
        lon = np.linspace(-100, -90, 50)
        self.coords = np.column_stack([lon, np.full_like(lon, 40.0)])
        self.total = 530.0

    def test_resample_is_even_and_scaled_to_route_distance(self):
        lat, lon, mile = resample_route(self.coords, self.total)
        self.assertAlmostEqual(mile[-1], self.total)
        self.assertLessEqual(len(mile), 3000)
        steps = np.diff(mile)
        self.assertAlmostEqual(steps.max(), steps.min(), places=6)
        self.assertAlmostEqual(lon[0], -100)
        self.assertAlmostEqual(lon[-1], -90)

    def test_stations_inside_corridor_get_mile_markers(self):
        lat, lon, mile = resample_route(self.coords, self.total)
        st_lat = np.array([40.02, 40.5, 39.0, 40.0])
        st_lon = np.array([-95.0, -95.0, -95.0, -99.0])
        idx, miles, off = stations_near_route(st_lat, st_lon, lat, lon, mile, corridor_miles=5)
        self.assertEqual(sorted(idx.tolist()), [0, 3])  # 40.5N is ~35 mi away, 39N ~69 mi
        by_idx = dict(zip(idx.tolist(), miles.tolist()))
        self.assertAlmostEqual(by_idx[0], 265, delta=5)
        self.assertAlmostEqual(by_idx[3], 53, delta=5)

    def test_no_stations_returns_empty(self):
        lat, lon, mile = resample_route(self.coords, self.total)
        idx, miles, off = stations_near_route(np.array([10.0]), np.array([-50.0]), lat, lon, mile, 5)
        self.assertEqual(len(idx), 0)
