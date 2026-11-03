"""Compose app routes here; keep feature-specific routing inside each app."""
from django.urls import include, path

urlpatterns = [
    # Each app owns the route names and views below its included prefix.
    path("", include("core.urls")),
    # Keep the foundation's namespaced links alongside launch URL names.
    path("", include(("core.urls", "core"), namespace="core")),
    path("accounts/", include("accounts.urls")),
]

# Add admin.site.urls after the agreed user model and database are configured.
