"""Enforce the ERD's typed item/version link even for direct database writes.

The ordinary Django item FK supplies ORM relations. This additional composite FK
has no model-state counterpart; preserve it explicitly in future schema changes.
Both referenced and referencing tables/columns are defined by migration 0001.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("reference", "0001_initial")]
    operations = [migrations.RunSQL(
        sql="""
            ALTER TABLE content_version
            ADD CONSTRAINT content_version_item_kind_fk
            FOREIGN KEY (item_id, kind)
            REFERENCES content_item (item_id, kind)
            DEFERRABLE INITIALLY IMMEDIATE
        """,
        reverse_sql="""
            ALTER TABLE content_version
            DROP CONSTRAINT content_version_item_kind_fk
        """,
    )]
