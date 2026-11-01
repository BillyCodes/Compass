from django.urls import path

from .views import HomeView

# Templates use core:home rather than hard-coding the home URL.
app_name = "core"
# This empty path becomes / because config.urls includes core at the root.
urlpatterns = [path("", HomeView.as_view(), name="home")]
