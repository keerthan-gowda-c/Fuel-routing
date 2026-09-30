from django.test import SimpleTestCase

from routing.errors import LocationError
from routing.geocoding import ApiCalls, resolve_location


class GeocodingTests(SimpleTestCase):
    def test_lat_lon(self):
        loc = resolve_location("41.8781, -87.6298")
        self.assertEqual((loc.source, loc.lat, loc.lon), ("coordinates", 41.8781, -87.6298))

    def test_zip_is_local(self):
        calls = ApiCalls()
        loc = resolve_location("60601", calls)
        self.assertEqual(loc.source, "zip")
        self.assertAlmostEqual(loc.lat, 41.88, delta=0.05)
        self.assertEqual(calls.count, 0)

    def test_city_state_is_local_and_flexible(self):
        calls = ApiCalls()
        for text in ["Chicago, IL", "chicago,il", "Chicago, IL, USA"]:
            loc = resolve_location(text, calls)
            self.assertEqual(loc.source, "city")
            self.assertAlmostEqual(loc.lon, -87.65, delta=0.15)
        self.assertEqual(calls.count, 0)

    def test_abbreviations_and_spacing_normalised(self):
        self.assertEqual(resolve_location("St. Louis, MO").source, "city")
        self.assertEqual(resolve_location("De Forest, WI").source, "city")

    def test_outside_usa_rejected(self):
        with self.assertRaises(LocationError):
            resolve_location("51.5074, -0.1278")  # London

    def test_empty_rejected(self):
        with self.assertRaises(LocationError):
            resolve_location("   ")
