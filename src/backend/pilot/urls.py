from django.urls import path

from . import api, views

app_name = "pilot"
urlpatterns = [
    path("resume/", views.resume_upload, name="resume-upload"),
    path("resume/<uuid:import_id>/review/", views.resume_review, name="resume-review"),
    path("progress/save/", views.save_progress, name="save-progress"),
    path("postings/", views.posting_create, name="posting-create"),
    path("postings/<uuid:posting_id>/run/", views.posting_run, name="posting-run"),
    # JSON contract; every route resolves the student from the session only.
    path("api/csrf", api.csrf, name="api-csrf"),
    path("api/register", api.register, name="api-register"),
    path("api/login", api.login_api, name="api-login"),
    path("api/logout", api.logout_api, name="api-logout"),
    path("api/me", api.me, name="api-me"),
    path("api/dashboard-data", api.dashboard_data, name="api-dashboard"),
    path("api/skills", api.skills_catalog, name="api-skills"),
    path("api/me/skills", api.my_skills, name="api-my-skills"),
    path("api/me/skills/<uuid:skill_id>", api.my_skill, name="api-my-skill"),
    path("api/comparisons", api.comparisons, name="api-comparisons"),
]
