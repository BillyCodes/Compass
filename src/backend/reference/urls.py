from django.urls import path
from . import views
app_name = "reference"
urlpatterns = [
    path("field-notes/", views.field_notes, name="notes"),
    path("field-notes/<uuid:version_id>/", views.field_note_detail, name="note"),
    path("library/<uuid:version_id>/", views.learning_detail, name="learning"),
]
