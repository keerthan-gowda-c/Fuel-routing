"""Cheapest fuel plan for a 1-D route with a tank of limited range.

Classic "gas station problem". The greedy below is optimal for this setting:

  At a station, look ahead one full tank.
    * If a cheaper station (or the destination, which costs $0) is reachable, buy only
      enough to get there - never pay more now for fuel a cheaper stop can supply.
    * Otherwise fill the tank and continue to the cheapest station in reach
      (farthest one on ties, since it extends reach the most).
  At the start no fuel can be bought, so head for the cheapest station within the initial fuel.

Works in miles of range internally; converts to gallons/dollars with `mpg` at the end.
"""
from dataclasses import dataclass

from .errors import InfeasibleRoute

EPS = 1e-9


@dataclass
class PlannedStop:
    station: int  # index into the arrays passed in
    mile: float
    price: float
    gallons: float
    cost: float
    tank_on_arrival_miles: float


@dataclass
class FuelPlan:
    stops: list
    total_cost: float
    total_gallons: float


def plan_fuel_stops(miles, prices, total_miles, range_miles=500.0, mpg=10.0, start_fuel_miles=None):
    order = sorted(range(len(miles)), key=lambda i: (miles[i], prices[i]))
    m = [float(miles[i]) for i in order] + [float(total_miles)]
    p = [float(prices[i]) for i in order] + [0.0]
    n = len(order)  # index of the destination pseudo-station
    R = float(range_miles)
    fuel = R if start_fuel_miles is None else min(float(start_fuel_miles), R)

    pos, cur, arrival, stops = 0.0, -1, fuel, []

    def cheapest(lo, hi_mile):
        best = None
        for j in range(lo, n):
            if m[j] > hi_mile + EPS:
                break
            if best is None or p[j] <= p[best]:  # <= keeps the farthest of equal prices
                best = j
        return best

    while True:
        if cur == -1:
            if total_miles - pos <= fuel + EPS:
                break
            nxt = cheapest(0, pos + fuel)
            if nxt is None:
                raise InfeasibleRoute(
                    f"No fuel station within {fuel:.0f} miles of the start; cannot begin the trip.", at_mile=0.0
                )
            buy = 0.0
        else:
            nxt = None
            for j in range(cur + 1, n + 1):
                if m[j] > pos + R + EPS:
                    break
                if p[j] < p[cur]:
                    nxt = j
                    break
            if nxt is not None:
                buy = max(0.0, (m[nxt] - pos) - fuel)
            else:
                nxt = cheapest(cur + 1, pos + R)
                if nxt is None:
                    raise InfeasibleRoute(
                        f"No fuel station within {R:.0f} miles after mile {pos:.0f}; the vehicle cannot complete the route.",
                        at_mile=pos,
                    )
                buy = R - fuel
            if buy > EPS:
                gal = buy / mpg
                stops.append(PlannedStop(order[cur], pos, p[cur], gal, gal * p[cur], arrival))
            fuel += buy

        fuel = max(0.0, fuel - (m[nxt] - pos))
        pos, cur, arrival = m[nxt], nxt, fuel
        if cur == n:
            break

    return FuelPlan(stops, sum(s.cost for s in stops), sum(s.gallons for s in stops))
