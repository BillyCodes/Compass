from django.urls import path

from . import maintenance_views


app_name = "maintenance"

urlpatterns = [
    path(
        "",
        maintenance_views.dashboard,
        name="dashboard",
    ),
    path(
        "create/",
        maintenance_views.create_content,
        name="create_content",
    ),
    path(
        "edit/<uuid:version_id>/",
        maintenance_views.edit_content,
        name="edit_content",
    ),
    path(
        "edit/<uuid:version_id>/sources/add/",
        maintenance_views.add_source,
        name="add_source",
    ),
]