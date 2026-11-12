from django.urls import path

from . import maintenance_source_views, maintenance_views, maintenance_curation_views

from . import maintenance_publication_views


from . import maintenance_requirement_views

from . import maintenance_detail_views

from . import maintenance_skill_views
from . import maintenance_lifecycle_views

app_name = "maintenance"

urlpatterns = [
    path("import/onet/", maintenance_curation_views.onet_import, name="onet_import"),
    path("preview/<uuid:version_id>/", maintenance_curation_views.preview, name="preview"),
    path("edit/<uuid:version_id>/sources/reuse/", maintenance_curation_views.reuse_source, name="reuse_source"),
    path("edit/<uuid:version_id>/field-note/", maintenance_curation_views.field_note, name="field_note"),
    path("successor/<uuid:version_id>/", maintenance_lifecycle_views.successor, name="successor"),
    path("retire/<uuid:version_id>/", maintenance_lifecycle_views.retire, name="retire"),
    path(
        "",
        maintenance_views.dashboard,
        name="dashboard",
    ),
    path(
        "create/",
        maintenance_views.create_content,
        name="create_content",
    ),
    path(
        "edit/<uuid:version_id>/",
        maintenance_views.edit_content,
        name="edit_content",
    ),
    path(
        "edit/<uuid:version_id>/sources/add/",
        maintenance_views.add_source,
        name="add_source",
    ),
    path(
        "edit/<uuid:version_id>/sources/<uuid:source_id>/remove/",
        maintenance_source_views.remove_source,
        name="remove_source",
    ),
    path(
        "edit/<uuid:version_id>/sources/<uuid:source_id>/edit/",
        maintenance_source_views.edit_source,
        name="edit_source",
    ),
    path(
        "publish/<uuid:version_id>/",
        maintenance_publication_views.publish_content,
        name="publish_content",
    ),
     path(
        "edit/<uuid:version_id>/requirements/add/",
        maintenance_requirement_views.add_requirement,
        name="add_requirement",
    ),
     path(
        "edit/<uuid:version_id>/requirements/<uuid:skill_id>/remove/",
        maintenance_requirement_views.remove_requirement,
        name="remove_requirement",
    ),
        path(
        "edit/<uuid:version_id>/companies/add/",
        maintenance_detail_views.add_company,
        name="add_company",
    ),
        path(
        "edit/<uuid:version_id>/job-details/",
        maintenance_detail_views.edit_job_details,
        name="edit_job_details",
    ),
        path(
        "edit/<uuid:version_id>/course-details/",
        maintenance_detail_views.edit_course_details,
        name="edit_course_details",
    ),
        path(
        "edit/<uuid:version_id>/skills/add/",
        maintenance_skill_views.add_skill_mapping,
        name="add_skill_mapping",
    ),
    path(
        "edit/<uuid:version_id>/skills/<uuid:skill_id>/remove/",
        maintenance_skill_views.remove_skill_mapping,
        name="remove_skill_mapping",
    ),
        path(
        "edit/<uuid:version_id>/resource-details/",
        maintenance_detail_views.edit_resource_details,
        name="edit_resource_details",
    ),

]
