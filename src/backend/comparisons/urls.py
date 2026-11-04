"""Student comparison routes."""
from django.urls import path

from .views import comparison_list

app_name = "comparisons"

urlpatterns = [
    path("", comparison_list, name="list"),
]