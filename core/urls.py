from django.urls import path

from . import api, views

urlpatterns = [
    # Public + auth
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Student pages
    path("welcome/", views.onboarding, name="onboarding"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("skillprint/", views.my_skillprint, name="skillprint"),
    path("skillprint/skill/<slug:skill_id>/level/", views.update_skill, name="update_skill"),
    path("skillprint/skill/<slug:skill_id>/remove/", views.remove_skill, name="remove_skill"),
    path("skillprint/course/", views.add_course, name="add_course"),
    path("skillprint/save/", views.save_progress, name="save_progress"),
    path("explore/", views.skill_explorer, name="explorer"),
    path("resume/", views.resume_upload, name="resume_upload"),
    path("resume/<int:pk>/review/", views.resume_review, name="resume_review"),
    path("compare/", views.compare, name="compare"),
    path("compare/career/<int:pk>/", views.run_career_compare, name="run_career_compare"),
    path("compare/posting/<int:pk>/", views.run_posting_compare, name="run_posting_compare"),
    path("results/<uuid:pk>/", views.result_detail, name="result_detail"),
    path("journey/", views.journey, name="journey"),
    path("field-notes/", views.field_notes, name="field_notes"),
    path("field-notes/<int:pk>/", views.field_note_detail, name="field_note_detail"),
    path("profile/", views.profile, name="profile"),
    # JSON contract (blueprint §7)
    path("api/csrf", api.csrf, name="api_csrf"),
    path("api/register", api.register, name="api_register"),
    path("api/login", api.login_api, name="api_login"),
    path("api/logout", api.logout_api, name="api_logout"),
    path("api/me", api.me, name="api_me"),
    path("api/dashboard-data", api.dashboard_data, name="api_dashboard"),
    path("api/skills", api.skills_catalog, name="api_skills"),
    path("api/me/skills", api.my_skills, name="api_my_skills"),
    path("api/me/skills/<slug:skill_id>", api.my_skill, name="api_my_skill"),
    path("api/comparisons", api.comparisons, name="api_comparisons"),
]
