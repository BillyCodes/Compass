"""Account routes live under the /accounts/ project prefix."""
from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import EmailLoginView, profile

app_name = "accounts"
urlpatterns = [
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", profile, name="profile"),
    path("students/<uuid:student_id>/", profile, name="student-detail"),
]
