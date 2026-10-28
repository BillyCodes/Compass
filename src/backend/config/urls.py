"""Compose app routes here; keep feature-specific routing inside each app."""
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
]

# Add admin.site.urls after the agreed user model and database are configured.
