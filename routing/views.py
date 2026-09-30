import json
from urllib.parse import urlencode
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .errors import PlannerError
from .planner import plan_trip

 # name: (min, max)
_OPTIONS = { 
    "range_miles": (50, 2000),
    "mpg": (1, 100),
    "start_fuel_miles": (0, 2000),
    "corridor_miles": (1, 50),
}

class BadRequest(PlannerError):
    status = 400


def _params(request):
    if request.method == "POST" and request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except ValueError as exc:
            raise BadRequest("Body must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise BadRequest("Body must be a JSON object.")
    else:
        data = request.POST if request.method == "POST" else request.GET

    if not data.get("start") or not data.get("finish"):
        raise BadRequest("Both 'start' and 'finish' are required (e.g. 'Chicago, IL').")

    kwargs = {}
    for name, (lo, hi) in _OPTIONS.items():
        raw = data.get(name)
        if raw in (None, ""):
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError) as exc:
            raise BadRequest(f"'{name}' must be a number.") from exc
        if not lo <= val <= hi:
            raise BadRequest(f"'{name}' must be between {lo} and {hi}.")
        kwargs[name] = val
    if kwargs.get("start_fuel_miles", 0) > kwargs.get("range_miles", settings.DEFAULT_RANGE_MILES):
        raise BadRequest("'start_fuel_miles' cannot exceed 'range_miles'.")
    return str(data["start"]), str(data["finish"]), kwargs

def _error(exc):
    return JsonResponse({"error": str(exc)}, status=exc.status)

@csrf_exempt
@require_http_methods(["GET", "POST"])
def route_api(request):
# GET /api/route/?start=...&finish=...   or   POST JSON {"start": ..., "finish": ...}
    try:
        start, finish, kwargs = _params(request)
        result = plan_trip(start, finish, **kwargs)
    except PlannerError as exc:
        return _error(exc)
    query = urlencode({"start": start, "finish": finish, **{k: v for k, v in kwargs.items()}})
    result["map_url"] = request.build_absolute_uri(reverse("route-map") + "?" + query)
    return JsonResponse(result)

@require_http_methods(["GET"])
def route_map(request):
    try:
        start, finish, kwargs = _params(request)
        result = plan_trip(start, finish, **kwargs)
    except PlannerError as exc:
        return render(request, "routing/map.html", {"error": str(exc)}, status=exc.status)
    return render(request, "routing/map.html", {"result": result})

def health(request):
    return JsonResponse({"status": "ok"})
