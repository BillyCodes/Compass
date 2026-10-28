"""Compose app routes here; keep feature-specific routing inside each app."""
from django.urls import include, path

urlpatterns = [
    # Each app owns the route names and views below its included prefix.
    path("", include("core.urls")),
    # An included empty URL list reserves the app boundary; it exposes no page.
    path("accounts/", include("accounts.urls")),
]

# Add admin.site.urls after the agreed user model and database are configured.
