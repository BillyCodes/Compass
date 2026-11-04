from django.urls import path
from . import views
app_name = "skills"
urlpatterns = [
    path("skillprint/", views.skillprint, name="skillprint"),
    path("skillprint/skills/<uuid:skill_id>/level/", views.update_skill, name="update-skill"),
    path("skillprint/skills/<uuid:skill_id>/remove/", views.remove_skill, name="remove-skill"),
    path("skillprint/courses/", views.add_course, name="add-course"),
    path("skillprint/courses/<uuid:item_id>/remove/", views.remove_course, name="remove-course"),
    path("explore/", views.explorer, name="explorer"),
]
