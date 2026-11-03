"""Compose app routes here; keep feature-specific routing inside each app."""
from django.urls import include, path

urlpatterns = [
    # Each app owns the route names and views below its included prefix.
    path("", include("core.urls")),
    # Account routes expose sign-in, POST-only sign-out, and owned profiles.
    path("accounts/", include("accounts.urls")),
]

# Admin routes remain deferred until the corresponding forms and access rules are ready.
