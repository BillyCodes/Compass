"""Database-level review, revision, publication, and published-history guards.

Services own request authorization; these PostgreSQL row triggers independently
protect integrity for ordinary ORM/SQL writes. Trusted DB administrators still
control DDL. Keep these functions/triggers explicit in future schema migrations.
"""
from django.db import migrations

FORWARD = r"""
CREATE FUNCTION reference_is_editor(account_uuid uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM account a JOIN account_role ar ON ar.account_id = a.account_id
        JOIN role r ON r.role_id = ar.role_id
        WHERE a.account_id = account_uuid AND a.is_active
          AND r.role_name IN ('maintainer', 'administrator')
    );
$$;

CREATE FUNCTION reference_assert_publishable(version_uuid uuid, publisher_uuid uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE v content_version%ROWTYPE; r content_review%ROWTYPE;
BEGIN
    SELECT * INTO v FROM content_version WHERE version_id = version_uuid;
    IF NOT FOUND OR v.status <> 'draft' THEN
        RAISE EXCEPTION 'Only a draft can be published.' USING ERRCODE = '23514';
    END IF;
    IF NOT reference_is_editor(publisher_uuid) THEN
        RAISE EXCEPTION 'Publication requires an active maintainer or administrator.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM content_item WHERE item_id = v.item_id AND retired_at IS NOT NULL) THEN
        RAISE EXCEPTION 'The content item is retired.' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO r FROM content_review
    WHERE version_id = v.version_id AND reviewed_revision = v.draft_revision
    ORDER BY reviewed_at DESC, review_id DESC LIMIT 1;
    IF NOT FOUND OR r.decision <> 'approved' OR r.reviewer_id = v.created_by_id
       OR NOT reference_is_editor(r.reviewer_id) THEN
        RAISE EXCEPTION 'The current draft needs a latest independent approval from an active reviewer.' USING ERRCODE = '23514';
    END IF;
    IF btrim(v.title) = '' OR btrim(v.body) = '' THEN
        RAISE EXCEPTION 'A title and body are required.' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM content_source WHERE version_id = v.version_id) THEN
        RAISE EXCEPTION 'At least one reference source is required.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM content_source cs JOIN reference_source rs ON rs.source_id = cs.source_id
        WHERE cs.version_id = v.version_id
          AND (btrim(rs.source_title) = '' OR btrim(rs.source_url_or_identifier) = '')
    ) THEN
        RAISE EXCEPTION 'Source titles and identifiers must be meaningful.' USING ERRCODE = '23514';
    END IF;
    -- Serialize against concurrent skill retirement while validating publication.
    PERFORM s.skill_id FROM skill s WHERE s.skill_id IN (
        SELECT skill_id FROM content_requirement WHERE version_id = v.version_id
        UNION SELECT skill_id FROM content_skill WHERE version_id = v.version_id
    ) ORDER BY s.skill_id FOR SHARE;
    IF EXISTS (
        SELECT 1 FROM skill s WHERE s.status <> 'active' AND s.skill_id IN (
            SELECT skill_id FROM content_requirement WHERE version_id = v.version_id
            UNION SELECT skill_id FROM content_skill WHERE version_id = v.version_id
        )
    ) THEN
        RAISE EXCEPTION 'Retired skills cannot be published as current requirements or coverage.' USING ERRCODE = '23514';
    END IF;
    IF v.kind IN ('career', 'job') AND NOT EXISTS (
        SELECT 1 FROM content_requirement WHERE version_id = v.version_id AND weight > 0
    ) THEN
        RAISE EXCEPTION 'Career/job content needs requirements with at least one positive weight.' USING ERRCODE = '23514';
    END IF;
    IF v.kind IN ('course', 'resource') AND NOT EXISTS (
        SELECT 1 FROM content_skill WHERE version_id = v.version_id AND coverage_level > 0
    ) THEN
        RAISE EXCEPTION 'Learning content needs at least one positive skill coverage mapping.' USING ERRCODE = '23514';
    END IF;
    IF v.kind = 'course' AND NOT EXISTS (
        SELECT 1 FROM content_details WHERE version_id = v.version_id
          AND (btrim(course_code) <> '' OR btrim(provider) <> '')
    ) THEN
        RAISE EXCEPTION 'A course needs a course code or provider.' USING ERRCODE = '23514';
    END IF;
    IF v.kind = 'resource' AND NOT EXISTS (
        SELECT 1 FROM content_details WHERE version_id = v.version_id AND resource_url ~* '^https?://'
    ) THEN
        RAISE EXCEPTION 'A learning resource needs an HTTP or HTTPS URL.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM content_details WHERE version_id = v.version_id AND expires_at <= statement_timestamp()) THEN
        RAISE EXCEPTION 'Expired content cannot be published.' USING ERRCODE = '23514';
    END IF;
END;
$$;

CREATE FUNCTION reference_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' OR NEW.published_by_id IS NOT NULL OR NEW.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'New versions must start as unpublished drafts.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' OR OLD.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'Published history cannot be deleted.' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF ROW(NEW.version_id,NEW.item_id,NEW.kind,NEW.version_no,NEW.created_by_id)
       IS DISTINCT FROM ROW(OLD.version_id,OLD.item_id,OLD.kind,OLD.version_no,OLD.created_by_id) THEN
        RAISE EXCEPTION 'Version identity and authorship cannot be reassigned.' USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'draft' OR OLD.published_at IS NOT NULL THEN
        IF ROW(NEW.title,NEW.body,NEW.draft_revision,NEW.published_by_id,NEW.published_at)
           IS DISTINCT FROM ROW(OLD.title,OLD.body,OLD.draft_revision,OLD.published_by_id,OLD.published_at)
           OR NOT (NEW.status = OLD.status OR (OLD.status = 'published' AND NEW.status = 'retired')) THEN
            RAISE EXCEPTION 'Published content is immutable; create a successor version.' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status = 'published' THEN
        IF ROW(NEW.title,NEW.body,NEW.draft_revision) IS DISTINCT FROM ROW(OLD.title,OLD.body,OLD.draft_revision) THEN
            RAISE EXCEPTION 'Publish the reviewed draft without editing it in the same operation.' USING ERRCODE = '23514';
        END IF;
        PERFORM reference_assert_publishable(OLD.version_id, NEW.published_by_id);
        IF NEW.published_at IS NULL THEN
            RAISE EXCEPTION 'Publication time is required.' USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.status = 'draft' THEN
        IF NEW.published_by_id IS NOT NULL OR NEW.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'Drafts cannot have publication attribution.' USING ERRCODE = '23514';
        END IF;
        IF ROW(NEW.title,NEW.body) IS DISTINCT FROM ROW(OLD.title,OLD.body) THEN
            NEW.draft_revision := OLD.draft_revision + 1;
        ELSIF NEW.draft_revision <> OLD.draft_revision AND NEW.draft_revision <> OLD.draft_revision + 1 THEN
            RAISE EXCEPTION 'Draft revisions must advance one step.' USING ERRCODE = '23514';
        END IF;
    ELSE
        RAISE EXCEPTION 'Only published versions can be retired.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER reference_version_guard BEFORE INSERT OR UPDATE OR DELETE ON content_version
FOR EACH ROW EXECUTE FUNCTION reference_version_guard();

CREATE FUNCTION reference_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE version_uuid uuid; v content_version%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.version_id IS DISTINCT FROM OLD.version_id THEN
        RAISE EXCEPTION 'A reference row cannot be moved to a different version.' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN version_uuid := OLD.version_id; ELSE version_uuid := NEW.version_id; END IF;
    SELECT * INTO v FROM content_version WHERE version_id = version_uuid FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Content version does not exist.' USING ERRCODE = '23503'; END IF;
    IF v.status <> 'draft' OR v.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'Published reference data is immutable.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM content_item WHERE item_id = v.item_id AND retired_at IS NOT NULL) THEN
        RAISE EXCEPTION 'The content item is retired.' USING ERRCODE = '23514';
    END IF;
    UPDATE content_version SET draft_revision = draft_revision + 1 WHERE version_id = version_uuid;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;
CREATE TRIGGER requirement_draft_guard BEFORE INSERT OR UPDATE OR DELETE ON content_requirement
FOR EACH ROW EXECUTE FUNCTION reference_child_guard();
CREATE TRIGGER mapping_draft_guard BEFORE INSERT OR UPDATE OR DELETE ON content_skill
FOR EACH ROW EXECUTE FUNCTION reference_child_guard();
CREATE TRIGGER source_link_draft_guard BEFORE INSERT OR UPDATE OR DELETE ON content_source
FOR EACH ROW EXECUTE FUNCTION reference_child_guard();
CREATE TRIGGER details_draft_guard BEFORE INSERT OR UPDATE OR DELETE ON content_details
FOR EACH ROW EXECUTE FUNCTION reference_child_guard();

CREATE FUNCTION reference_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v content_version%ROWTYPE; last_time timestamptz;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Reviews are append-only; submit a new decision.' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v FROM content_version WHERE version_id = NEW.version_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Content version does not exist.' USING ERRCODE = '23503'; END IF;
    IF v.status <> 'draft' OR NEW.reviewed_revision <> v.draft_revision THEN
        RAISE EXCEPTION 'Review the current draft revision only.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM content_item WHERE item_id = v.item_id AND retired_at IS NOT NULL) THEN
        RAISE EXCEPTION 'The content item is retired.' USING ERRCODE = '23514';
    END IF;
    IF NEW.reviewer_id = v.created_by_id OR NOT reference_is_editor(NEW.reviewer_id) THEN
        RAISE EXCEPTION 'Review requires an active independent maintainer or administrator.' USING ERRCODE = '23514';
    END IF;
    SELECT max(reviewed_at) INTO last_time FROM content_review
    WHERE version_id = NEW.version_id AND reviewed_revision = NEW.reviewed_revision;
    IF last_time IS NOT NULL AND NEW.reviewed_at <= last_time THEN
        RAISE EXCEPTION 'A new review must follow the previous decision.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER reference_review_guard BEFORE INSERT OR UPDATE OR DELETE ON content_review
FOR EACH ROW EXECUTE FUNCTION reference_review_guard();

CREATE FUNCTION reference_shared_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v content_version%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
    IF TG_TABLE_NAME = 'reference_source' THEN
        FOR v IN SELECT cv.* FROM content_version cv WHERE cv.version_id IN (
            SELECT version_id FROM content_source WHERE source_id = OLD.source_id
        ) ORDER BY cv.version_id FOR UPDATE LOOP
            IF v.status <> 'draft' OR v.published_at IS NOT NULL THEN
                RAISE EXCEPTION 'A source used by published content is immutable.' USING ERRCODE = '23514';
            END IF;
            UPDATE content_version SET draft_revision = draft_revision + 1 WHERE version_id = v.version_id;
        END LOOP;
    ELSE
        FOR v IN SELECT cv.* FROM content_version cv WHERE cv.version_id IN (
            SELECT version_id FROM content_details WHERE company_id = OLD.company_id
        ) ORDER BY cv.version_id FOR UPDATE LOOP
            IF v.status <> 'draft' OR v.published_at IS NOT NULL THEN
                RAISE EXCEPTION 'A company used by published content is immutable.' USING ERRCODE = '23514';
            END IF;
            UPDATE content_version SET draft_revision = draft_revision + 1 WHERE version_id = v.version_id;
        END LOOP;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;
CREATE TRIGGER reference_source_history_guard BEFORE UPDATE OR DELETE ON reference_source
FOR EACH ROW EXECUTE FUNCTION reference_shared_guard();
CREATE TRIGGER company_history_guard BEFORE UPDATE OR DELETE ON company
FOR EACH ROW EXECUTE FUNCTION reference_shared_guard();
"""

REVERSE = """
DROP TRIGGER company_history_guard ON company;
DROP TRIGGER reference_source_history_guard ON reference_source;
DROP FUNCTION reference_shared_guard();
DROP TRIGGER reference_review_guard ON content_review;
DROP FUNCTION reference_review_guard();
DROP TRIGGER details_draft_guard ON content_details;
DROP TRIGGER source_link_draft_guard ON content_source;
DROP TRIGGER mapping_draft_guard ON content_skill;
DROP TRIGGER requirement_draft_guard ON content_requirement;
DROP FUNCTION reference_child_guard();
DROP TRIGGER reference_version_guard ON content_version;
DROP FUNCTION reference_version_guard();
DROP FUNCTION reference_assert_publishable(uuid, uuid);
DROP FUNCTION reference_is_editor(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [("reference", "0005_contentreview")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
