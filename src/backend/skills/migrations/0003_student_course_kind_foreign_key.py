"""A selected course must reference an actual course CONTENT_ITEM."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("skills", "0002_studentcourse")]
    operations = [migrations.RunSQL(
        sql="""ALTER TABLE student_course ADD CONSTRAINT student_course_item_kind_fk
               FOREIGN KEY (course_item_id, course_kind)
               REFERENCES content_item (item_id, kind)
               DEFERRABLE INITIALLY IMMEDIATE""",
        reverse_sql="ALTER TABLE student_course DROP CONSTRAINT student_course_item_kind_fk",
    )]
