"""Student skill and course routes."""
from django.urls import path

from .views import (
    student_course_remove,
    student_courses,
    student_skills,
)

app_name = "skills"

urlpatterns = [
    path("", student_skills, name="student-skills"),
    path("courses/", student_courses, name="student-courses"),
    path(
        "courses/<uuid:course_item_id>/remove/",
        student_course_remove,
        name="student-course-remove",
    ),
]