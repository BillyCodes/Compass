from django.urls import path
from . import views
app_name = "comparisons"
urlpatterns = [
    path("compare/", views.compare, name="compare"),
    path("compare/<uuid:version_id>/", views.run, name="run"),
    path("results/<uuid:match_id>/", views.detail, name="detail"),
    path("results/<uuid:match_id>/delete/", views.remove, name="delete"),
    path("journey/", views.journey, name="journey"),
]
