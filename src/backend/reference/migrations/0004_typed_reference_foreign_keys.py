"""Preserve the ERD's version-kind identity for all typed reference children.

Django supplies ordinary version FKs for ORM navigation. These additional
PostgreSQL constraints guard writes that bypass model/service validation.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("reference", "0003_company_referencesource_contentdetails_and_more")]
    operations = [
        migrations.RunSQL(
            sql=f"""
                ALTER TABLE {table}
                ADD CONSTRAINT {table}_version_kind_fk
                FOREIGN KEY (version_id, kind)
                REFERENCES content_version (version_id, kind)
                DEFERRABLE INITIALLY IMMEDIATE
            """,
            reverse_sql=f"ALTER TABLE {table} DROP CONSTRAINT {table}_version_kind_fk",
        )
        for table in ("content_requirement", "content_skill", "content_details")
    ]
