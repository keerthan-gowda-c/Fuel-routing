class PlannerError(Exception):
    """Base class; carries the HTTP status the API should answer with."""

    status = 400


class LocationError(PlannerError):
    status = 400


class RoutingError(PlannerError):
    status = 502


class InfeasibleRoute(PlannerError):
    status = 422

    def __init__(self, message, at_mile=None):
        super().__init__(message)
        self.at_mile = at_mile
