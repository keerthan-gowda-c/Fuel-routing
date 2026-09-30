from django.urls import path

from . import views

urlpatterns = [
    path("api/route/", views.route_api, name="route-api"),
    path("map/", views.route_map, name="route-map"),
    path("health/", views.health, name="health"),
]
