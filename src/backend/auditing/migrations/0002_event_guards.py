"""Protect minimal metadata, event history, and the one-calendar-year retention floor."""
from django.db import migrations

FORWARD = r"""
CREATE FUNCTION audit_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.occurred_at >= statement_timestamp() - interval '1 year' THEN
            RAISE EXCEPTION 'Audit events must be retained for one calendar year.' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        -- Django's deletion collector nulls links before deleting the parent.
        -- Permit link removal, but never replacement or restoration of attribution.
        IF (to_jsonb(NEW) - 'actor_account_id' - 'subject_account_id' - 'content_version_id')
           IS DISTINCT FROM (to_jsonb(OLD) - 'actor_account_id' - 'subject_account_id' - 'content_version_id')
           OR (NEW.actor_account_id IS DISTINCT FROM OLD.actor_account_id AND NEW.actor_account_id IS NOT NULL)
           OR (NEW.subject_account_id IS DISTINCT FROM OLD.subject_account_id AND NEW.subject_account_id IS NOT NULL)
           OR (NEW.content_version_id IS DISTINCT FROM OLD.content_version_id AND NEW.content_version_id IS NOT NULL) THEN
            RAISE EXCEPTION 'Audit events cannot be edited; only reference links may be cleared.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF jsonb_typeof(NEW.metadata) <> 'object' THEN
        RAISE EXCEPTION 'Audit metadata must be a minimal structured object.' USING ERRCODE = '23514';
    END IF;
    IF NEW.event_type IN ('role.assigned','role.removed') THEN
        IF (NEW.metadata - 'role_name') <> '{}'::jsonb
           OR NOT (NEW.metadata ? 'role_name')
           OR NEW.metadata->'role_name' NOT IN ('"student"'::jsonb,'"maintainer"'::jsonb,'"administrator"'::jsonb) THEN
            RAISE EXCEPTION 'Role events allow only a valid role_name.' USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.event_type = 'content.reviewed' THEN
        IF (NEW.metadata - 'decision' - 'reviewed_revision') <> '{}'::jsonb
           OR NOT (NEW.metadata ?& ARRAY['decision','reviewed_revision'])
           OR NEW.metadata->'decision' NOT IN ('"approved"'::jsonb,'"changes_requested"'::jsonb)
           OR jsonb_typeof(NEW.metadata->'reviewed_revision') <> 'number'
           OR NEW.metadata->>'reviewed_revision' !~ '^[1-9][0-9]{0,9}$' THEN
            RAISE EXCEPTION 'Review events allow only decision and a positive integer revision.' USING ERRCODE = '23514';
        END IF;
        IF (NEW.metadata->>'reviewed_revision')::numeric > 2147483647 THEN
            RAISE EXCEPTION 'Review revision exceeds the schema limit.' USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.metadata <> '{}'::jsonb THEN
        RAISE EXCEPTION 'This audit event type allows no additional metadata.' USING ERRCODE = '23514';
    END IF;
    IF NEW.event_type IN ('role.assigned','role.removed','account.activated','account.disabled') THEN
        IF NEW.subject_account_id IS NULL OR NEW.content_version_id IS NOT NULL THEN
            RAISE EXCEPTION 'Account events need a subject and no content link.' USING ERRCODE = '23514';
        END IF;
    ELSE
        IF NEW.content_version_id IS NULL OR NEW.subject_account_id IS NOT NULL THEN
            RAISE EXCEPTION 'Content events need a version and no subject account.' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.actor_account_id IS NULL AND NEW.event_type <> 'role.assigned' THEN
        RAISE EXCEPTION 'An actor is required except for trusted initial role assignment.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER audit_event_guard BEFORE INSERT OR UPDATE OR DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION audit_event_guard();
"""
REVERSE = """
DROP TRIGGER audit_event_guard ON audit_event;
DROP FUNCTION audit_event_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("auditing", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
