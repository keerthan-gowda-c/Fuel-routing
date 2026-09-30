import random
from functools import lru_cache

from django.test import SimpleTestCase

from routing.errors import InfeasibleRoute
from routing.optimizer import plan_fuel_stops


def brute_force_cost(miles, prices, total, R, start_fuel):
    """Exact DP over integer miles / integer tank levels (mpg = 1, so cost = miles * price)."""
    st = sorted(zip(miles, prices))
    n = len(st)
    INF = float("inf")

    @lru_cache(maxsize=None)
    def best(i, fuel):  # at station i (or -1 = start) holding `fuel`
        pos = 0 if i == -1 else st[i][0]
        price = INF if i == -1 else st[i][1]
        out = INF
        for buy in range(0, (R - fuel + 1) if i != -1 else 1):
            f = fuel + buy
            cost = buy * price if buy else 0
            if total - pos <= f:
                out = min(out, cost)
            for j in range(i + 1, n):
                d = st[j][0] - pos
                if d > f:
                    break
                out = min(out, cost + best(j, f - d))
        return out

    return best(-1, start_fuel)


class OptimizerTests(SimpleTestCase):
    def test_trip_within_starting_tank_needs_no_stops(self):
        plan = plan_fuel_stops([100], [3.0], total_miles=400, range_miles=500)
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.total_cost, 0)

    def test_single_stop_buys_only_what_is_needed(self):
        # 800 mi trip, full tank; stop at mile 300 must add 300 mi = 30 gal.
        plan = plan_fuel_stops([300], [3.0], total_miles=800, range_miles=500, mpg=10)
        self.assertEqual(len(plan.stops), 1)
        self.assertAlmostEqual(plan.stops[0].gallons, 30.0)
        self.assertAlmostEqual(plan.total_cost, 90.0)

    def test_prefers_cheap_station_and_skips_pricey_one(self):
        # Expensive stop at 100, cheap at 450: drive past the expensive one.
        plan = plan_fuel_stops([100, 450], [4.5, 2.5], total_miles=900, range_miles=500, mpg=10)
        self.assertEqual([s.mile for s in plan.stops], [450])
        self.assertAlmostEqual(plan.stops[0].gallons, 40.0)  # 450 to go, arrives with 50 mi -> +400 mi
        self.assertAlmostEqual(plan.total_cost, 100.0)

    def test_buys_just_enough_to_reach_cheaper_next_stop(self):
        plan = plan_fuel_stops([400, 700], [3.5, 2.0], total_miles=1150, range_miles=500, mpg=10)
        first, second = plan.stops
        self.assertAlmostEqual(first.gallons, 20.0)      # arrive with 100 mi, need 300 to reach 700 -> +200 mi
        self.assertAlmostEqual(second.gallons, 45.0)     # 450 mi left, arrive with 0
        self.assertAlmostEqual(plan.total_cost, 20 * 3.5 + 45 * 2.0)

    def test_fills_up_when_nothing_cheaper_is_ahead(self):
        plan = plan_fuel_stops([200, 650], [2.0, 3.0], total_miles=1000, range_miles=500, mpg=10)
        self.assertEqual([s.mile for s in plan.stops], [200, 650])
        self.assertAlmostEqual(plan.stops[0].gallons, 50 - 30)  # tank had 300 mi left -> top up 200 mi

    def test_gap_larger_than_range_is_infeasible(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([100], [3.0], total_miles=1000, range_miles=500)

    def test_no_station_reachable_from_start(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([600], [3.0], total_miles=900, range_miles=500)

    def test_partial_starting_tank(self):
        plan = plan_fuel_stops([50], [3.0], total_miles=300, range_miles=500, mpg=10, start_fuel_miles=100)
        self.assertAlmostEqual(plan.stops[0].gallons, 20.0)  # arrives with 50 mi, needs 250 to finish -> +200 mi
        self.assertAlmostEqual(plan.total_cost, 60.0)

    def test_matches_exact_dp_on_random_instances(self):
        rng = random.Random(7)
        for _ in range(400):
            R = rng.randint(4, 12)
            total = rng.randint(3, 45)
            k = rng.randint(0, 9)
            miles = [rng.randint(1, total - 1) for _ in range(k)] if total > 1 else []
            prices = [rng.randint(1, 9) for _ in miles]
            start = rng.randint(0, R)
            expected = brute_force_cost(tuple(miles), tuple(prices), total, R, start)
            try:
                got = plan_fuel_stops(miles, prices, total, range_miles=R, mpg=1, start_fuel_miles=start).total_cost
            except InfeasibleRoute:
                got = float("inf")
            self.assertAlmostEqual(got, expected, places=6, msg=f"R={R} total={total} miles={miles} prices={prices} start={start}")
