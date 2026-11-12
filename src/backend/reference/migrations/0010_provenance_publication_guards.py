"""Extend the existing direct-publication checks without rewriting history."""
from importlib import import_module

from django.db import migrations


base = import_module("reference.migrations.0008_direct_publication")
guards = import_module("reference.migrations.0006_publication_guards")

PROVENANCE = r"""
CREATE FUNCTION reference_assert_provenance(version_uuid uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE v content_version%ROWTYPE;
BEGIN
    SELECT * INTO v FROM content_version WHERE version_id = version_uuid;
    IF v.origin = 'legacy' THEN
        RAISE EXCEPTION 'Classify the existing draft origin before publication.' USING ERRCODE = '23514';
    END IF;
    IF v.origin = 'original' AND (v.kind <> 'insight' OR btrim(v.original_author) = '' OR NOT v.originality_confirmed) THEN
        RAISE EXCEPTION 'Original reflections need an author and confirmation of original authorship and cited borrowed material.' USING ERRCODE = '23514';
    END IF;
    IF v.origin IN ('external', 'original') AND EXISTS (
        SELECT 1 FROM content_source cs JOIN reference_source rs ON rs.source_id = cs.source_id
        WHERE cs.version_id = v.version_id AND (
            rs.provider NOT IN ('onet','bls','mit','other') OR btrim(rs.publisher) = ''
            OR rs.source_url !~* '^https?://' OR cs.usage = 'unknown'
            OR (cs.usage <> 'link' AND (btrim(rs.license_name) = '' OR rs.license_url !~* '^https?://' OR btrim(rs.attribution_text) = ''))
            OR (cs.usage IN ('adapted','interpretation') AND btrim(cs.changes) = '')
            OR (rs.provider = 'onet' AND (btrim(rs.source_version) = '' OR btrim(rs.external_id) = '' OR rs.file_sha256 !~ '^[a-f0-9]{64}$'))
            OR jsonb_typeof(rs.raw_metadata) <> 'object'
        )
    ) THEN
        RAISE EXCEPTION 'Complete source provenance: provider, publisher, URL, usage, applicable license/credit, adaptation notes and O*NET file identity.' USING ERRCODE = '23514';
    END IF;
END;
$$;
"""

# Reuse the frozen prior migration definitions, preserving all other checks.
publication = base.FORWARD.replace(
    "    IF NOT EXISTS (\n        SELECT 1 FROM content_source",
    "    IF v.origin <> 'original' AND NOT EXISTS (\n        SELECT 1 FROM content_source",
    1,
).replace("    PERFORM s.skill_id", "    PERFORM reference_assert_provenance(v.version_id);\n\n    PERFORM s.skill_id", 1)

old_guard = guards.FORWARD.split("CREATE FUNCTION reference_version_guard()", 1)[1].split("CREATE TRIGGER reference_version_guard", 1)[0]
old_guard = "CREATE OR REPLACE FUNCTION reference_version_guard()" + old_guard
new_guard = old_guard.replace("NEW.title,NEW.body", "NEW.title,NEW.body,NEW.origin,NEW.original_author,NEW.originality_confirmed").replace(
    "OLD.title,OLD.body", "OLD.title,OLD.body,OLD.origin,OLD.original_author,OLD.originality_confirmed")


class Migration(migrations.Migration):
    dependencies = [("reference", "0009_content_provenance")]
    operations = [migrations.RunSQL(
        sql=PROVENANCE + publication + new_guard,
        reverse_sql=old_guard + base.FORWARD + "DROP FUNCTION reference_assert_provenance(uuid);",
    )]
