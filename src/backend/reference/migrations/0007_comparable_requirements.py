"""New publications must contain at least one genuinely scored requirement."""
from django.db import migrations

FORWARD = """
ALTER FUNCTION reference_assert_publishable(uuid, uuid) RENAME TO reference_assert_publishable_base_v1;
CREATE FUNCTION reference_assert_publishable(version_uuid uuid, publisher_uuid uuid)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM reference_assert_publishable_base_v1(version_uuid, publisher_uuid);
    IF EXISTS (SELECT 1 FROM content_version WHERE version_id = version_uuid AND kind IN ('career','job'))
       AND NOT EXISTS (SELECT 1 FROM content_requirement WHERE version_id = version_uuid AND required_level > 0 AND weight > 0) THEN
        RAISE EXCEPTION 'Career/job publication needs a positive-level, positive-weight requirement.' USING ERRCODE = '23514';
    END IF;
END;
$$;
"""
REVERSE = """
DROP FUNCTION reference_assert_publishable(uuid, uuid);
ALTER FUNCTION reference_assert_publishable_base_v1(uuid, uuid) RENAME TO reference_assert_publishable;
"""


class Migration(migrations.Migration):
    dependencies = [("reference", "0006_publication_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
