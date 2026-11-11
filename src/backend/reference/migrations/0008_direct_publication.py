from django.db import migrations


APPROVAL_CHECK = """
    SELECT * INTO r FROM content_review
    WHERE version_id = v.version_id
      AND reviewed_revision = v.draft_revision
    ORDER BY reviewed_at DESC, review_id DESC
    LIMIT 1;

    IF NOT FOUND
       OR r.decision <> 'approved'
       OR r.reviewer_id = v.created_by_id
       OR NOT reference_is_editor(r.reviewer_id) THEN
        RAISE EXCEPTION
            'The current draft needs a latest independent approval from an active reviewer.'
            USING ERRCODE = '23514';
    END IF;
"""


FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION reference_assert_publishable_base_v1(
    version_uuid uuid,
    publisher_uuid uuid
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v content_version%ROWTYPE;
    r content_review%ROWTYPE;
BEGIN
    SELECT * INTO v
    FROM content_version
    WHERE version_id = version_uuid;

    IF NOT FOUND OR v.status <> 'draft' THEN
        RAISE EXCEPTION 'Only a draft can be published.'
            USING ERRCODE = '23514';
    END IF;

    IF NOT reference_is_editor(publisher_uuid) THEN
        RAISE EXCEPTION
            'Publication requires an active maintainer or administrator.'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM content_item
        WHERE item_id = v.item_id
          AND retired_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'The content item is retired.'
            USING ERRCODE = '23514';
    END IF;

    /* APPROVAL_CHECK */

    IF btrim(v.title) = '' OR btrim(v.body) = '' THEN
        RAISE EXCEPTION 'A title and body are required.'
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM content_source
        WHERE version_id = v.version_id
    ) THEN
        RAISE EXCEPTION 'At least one reference source is required.'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM content_source cs
        JOIN reference_source rs ON rs.source_id = cs.source_id
        WHERE cs.version_id = v.version_id
          AND (
              btrim(rs.source_title) = ''
              OR btrim(rs.source_url_or_identifier) = ''
          )
    ) THEN
        RAISE EXCEPTION
            'Source titles and identifiers must be meaningful.'
            USING ERRCODE = '23514';
    END IF;

    PERFORM s.skill_id
    FROM skill s
    WHERE s.skill_id IN (
        SELECT skill_id FROM content_requirement
        WHERE version_id = v.version_id
        UNION
        SELECT skill_id FROM content_skill
        WHERE version_id = v.version_id
    )
    ORDER BY s.skill_id
    FOR SHARE;

    IF EXISTS (
        SELECT 1 FROM skill s
        WHERE s.status <> 'active'
          AND s.skill_id IN (
              SELECT skill_id FROM content_requirement
              WHERE version_id = v.version_id
              UNION
              SELECT skill_id FROM content_skill
              WHERE version_id = v.version_id
          )
    ) THEN
        RAISE EXCEPTION
            'Retired skills cannot be published as current requirements or coverage.'
            USING ERRCODE = '23514';
    END IF;

    IF v.kind IN ('career', 'job') AND NOT EXISTS (
        SELECT 1 FROM content_requirement
        WHERE version_id = v.version_id AND weight > 0
    ) THEN
        RAISE EXCEPTION
            'Career/job content needs requirements with at least one positive weight.'
            USING ERRCODE = '23514';
    END IF;

    IF v.kind IN ('course', 'resource') AND NOT EXISTS (
        SELECT 1 FROM content_skill
        WHERE version_id = v.version_id AND coverage_level > 0
    ) THEN
        RAISE EXCEPTION
            'Learning content needs at least one positive skill coverage mapping.'
            USING ERRCODE = '23514';
    END IF;

    IF v.kind = 'course' AND NOT EXISTS (
        SELECT 1 FROM content_details
        WHERE version_id = v.version_id
          AND (
              btrim(course_code) <> ''
              OR btrim(provider) <> ''
          )
    ) THEN
        RAISE EXCEPTION 'A course needs a course code or provider.'
            USING ERRCODE = '23514';
    END IF;

    IF v.kind = 'resource' AND NOT EXISTS (
        SELECT 1 FROM content_details
        WHERE version_id = v.version_id
          AND resource_url ~* '^https?://'
    ) THEN
        RAISE EXCEPTION 'A learning resource needs an HTTP or HTTPS URL.'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM content_details
        WHERE version_id = v.version_id
          AND expires_at <= statement_timestamp()
    ) THEN
        RAISE EXCEPTION 'Expired content cannot be published.'
            USING ERRCODE = '23514';
    END IF;
END;
$$;
"""


FORWARD = FUNCTION_SQL.replace("/* APPROVAL_CHECK */", "")
REVERSE = FUNCTION_SQL.replace("/* APPROVAL_CHECK */", APPROVAL_CHECK)


class Migration(migrations.Migration):
    dependencies = [
        ("reference", "0007_comparable_requirements"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD,
            reverse_sql=REVERSE,
        ),
    ]