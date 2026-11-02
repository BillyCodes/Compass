"""Typed endpoints, same-target outcomes, and atomic immutable result snapshots.

Services authorize access. These PostgreSQL constraints guard ordinary row CRUD;
privileged database administrators remain in control of DDL and trigger settings.
"""
from django.db import migrations

FORWARD = r"""
ALTER TABLE match_result ADD CONSTRAINT match_target_kind_fk
    FOREIGN KEY (target_version_id, target_kind) REFERENCES content_version(version_id, kind) DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE recommendation ADD CONSTRAINT recommendation_version_kind_fk
    FOREIGN KEY (resource_version_id, resource_kind) REFERENCES content_version(version_id, kind) DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE match_skill_result ADD CONSTRAINT outcome_match_target_fk
    FOREIGN KEY (match_id, target_version_id) REFERENCES match_result(match_id, target_version_id) DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE match_skill_result ADD CONSTRAINT outcome_requirement_fk
    FOREIGN KEY (target_version_id, skill_id) REFERENCES content_requirement(version_id, skill_id) DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE match_skill_result ADD CONSTRAINT outcome_input_fk
    FOREIGN KEY (match_id, skill_id) REFERENCES match_input_skill(match_id, skill_id) DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION comparison_assert_complete(match_uuid uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE m match_result%ROWTYPE; expected_count integer; actual_reported integer;
    actual_relevant integer; actual_score numeric; actual_mandatory text;
BEGIN
    SELECT * INTO m FROM match_result WHERE match_id = match_uuid;
    -- Entire private-result deletion, including deletion with its student, is allowed.
    IF NOT FOUND THEN RETURN; END IF;
    IF NOT m.finalized THEN
        RAISE EXCEPTION 'A comparison must be finalized atomically.' USING ERRCODE = '23514';
    END IF;
    SELECT count(*) INTO expected_count FROM content_requirement WHERE version_id = m.target_version_id;
    IF expected_count = 0 OR
       (SELECT count(*) FROM match_input_skill WHERE match_id = match_uuid) <> expected_count OR
       (SELECT count(*) FROM match_skill_result WHERE match_id = match_uuid) <> expected_count OR
       EXISTS (SELECT 1 FROM match_input_skill i WHERE i.match_id = match_uuid AND NOT EXISTS (
           SELECT 1 FROM content_requirement r WHERE r.version_id = m.target_version_id AND r.skill_id = i.skill_id)) THEN
        RAISE EXCEPTION 'Save exactly one input and outcome per target requirement.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM match_skill_result o JOIN match_input_skill i ON i.match_id = o.match_id AND i.skill_id = o.skill_id
        JOIN content_requirement r ON r.version_id = o.target_version_id AND r.skill_id = o.skill_id
        WHERE o.match_id = match_uuid AND (
            o.status IS DISTINCT FROM CASE WHEN r.required_level = 0 THEN 'met'
                WHEN i.level_used IS NULL THEN 'unreported' WHEN i.level_used < r.required_level THEN 'gap' ELSE 'met' END
            OR o.gap IS DISTINCT FROM CASE WHEN r.required_level = 0 THEN 0
                WHEN i.level_used IS NULL THEN NULL ELSE greatest(r.required_level - i.level_used, 0) END)
    ) THEN
        RAISE EXCEPTION 'Outcomes must match the saved input and target requirement.' USING ERRCODE = '23514';
    END IF;
    SELECT count(*) FILTER (WHERE r.required_level > 0 AND (r.weight > 0 OR r.mandatory)),
           count(*) FILTER (WHERE r.required_level > 0 AND (r.weight > 0 OR r.mandatory) AND i.level_used IS NOT NULL),
           round(100 * sum(CASE WHEN r.required_level > 0 AND r.weight > 0
                    THEN r.weight * least(coalesce(i.level_used,0),r.required_level) * (60 / r.required_level) ELSE 0 END)
                 / nullif(60 * sum(CASE WHEN r.required_level > 0 AND r.weight > 0 THEN r.weight ELSE 0 END),0), 2),
           CASE WHEN NOT bool_or(r.mandatory) THEN 'not_applicable'
                WHEN bool_or(r.mandatory AND r.required_level > 0 AND i.level_used < r.required_level) THEN 'not_met'
                WHEN bool_or(r.mandatory AND r.required_level > 0 AND i.level_used IS NULL) THEN 'undetermined' ELSE 'met' END
    INTO actual_relevant, actual_reported, actual_score, actual_mandatory
    FROM content_requirement r JOIN match_input_skill i ON i.match_id = match_uuid AND i.skill_id = r.skill_id
    WHERE r.version_id = m.target_version_id;
    IF actual_score IS NULL OR actual_reported = 0 OR m.score IS DISTINCT FROM actual_score
       OR m.relevant_count <> actual_relevant OR m.reported_count <> actual_reported
       OR m.mandatory_status <> actual_mandatory THEN
        RAISE EXCEPTION 'Score, mandatory status, and completeness must match saved inputs.' USING ERRCODE = '23514';
    END IF;
    IF (SELECT count(*) FROM recommendation WHERE match_id = match_uuid) <> m.recommendation_count
       OR coalesce((SELECT max(priority_rank) FROM recommendation WHERE match_id = match_uuid),0) <> m.recommendation_count THEN
        RAISE EXCEPTION 'Save the complete ordered recommendation snapshot.' USING ERRCODE = '23514';
    END IF;
END;
$$;

CREATE FUNCTION comparison_result_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.finalized OR NEW.recommendation_count <> 0 THEN
            RAISE EXCEPTION 'Assemble a comparison before finalizing it.' USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM content_version v JOIN content_item i ON i.item_id = v.item_id
            WHERE v.version_id = NEW.target_version_id AND v.status = 'published' AND i.retired_at IS NULL)
            OR EXISTS (SELECT 1 FROM content_details WHERE version_id = NEW.target_version_id AND expires_at <= statement_timestamp())
            OR EXISTS (SELECT 1 FROM content_requirement r JOIN skill s ON s.skill_id = r.skill_id
                WHERE r.version_id = NEW.target_version_id AND s.status <> 'active') THEN
            RAISE EXCEPTION 'Compare available published targets with active skills only.' USING ERRCODE = '23514';
        END IF;
    ELSE
        IF OLD.finalized OR NOT NEW.finalized OR
            (to_jsonb(NEW) - 'finalized' - 'recommendation_count') IS DISTINCT FROM
            (to_jsonb(OLD) - 'finalized' - 'recommendation_count') THEN
            RAISE EXCEPTION 'Saved comparisons are immutable; create a new comparison.' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER comparison_result_guard BEFORE INSERT OR UPDATE ON match_result
FOR EACH ROW EXECUTE FUNCTION comparison_result_guard();

CREATE FUNCTION comparison_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sealed boolean;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Comparison snapshots cannot be edited.' USING ERRCODE = '23514';
    END IF;
    SELECT finalized INTO sealed FROM match_result WHERE match_id = NEW.match_id FOR UPDATE;
    IF NOT FOUND OR sealed THEN
        RAISE EXCEPTION 'Add snapshots only while assembling a comparison.' USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'recommendation' THEN
      IF (
        NOT EXISTS (SELECT 1 FROM content_version v JOIN content_item i ON i.item_id = v.item_id
            WHERE v.version_id = NEW.resource_version_id AND v.status = 'published' AND i.retired_at IS NULL)
        OR EXISTS (SELECT 1 FROM content_details WHERE version_id = NEW.resource_version_id AND expires_at <= statement_timestamp())
        OR EXISTS (SELECT 1 FROM content_skill c JOIN skill s ON s.skill_id = c.skill_id
            WHERE c.version_id = NEW.resource_version_id AND s.status <> 'active')
    ) THEN
        RAISE EXCEPTION 'Recommend available published learning content with active skills only.' USING ERRCODE = '23514';
      END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER comparison_input_guard BEFORE INSERT OR UPDATE ON match_input_skill
FOR EACH ROW EXECUTE FUNCTION comparison_child_guard();
CREATE TRIGGER comparison_outcome_guard BEFORE INSERT OR UPDATE ON match_skill_result
FOR EACH ROW EXECUTE FUNCTION comparison_child_guard();
CREATE TRIGGER comparison_recommendation_guard BEFORE INSERT OR UPDATE ON recommendation
FOR EACH ROW EXECUTE FUNCTION comparison_child_guard();

CREATE FUNCTION comparison_deferred_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN PERFORM comparison_assert_complete(OLD.match_id);
    ELSE PERFORM comparison_assert_complete(NEW.match_id); END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER comparison_result_complete AFTER INSERT OR UPDATE ON match_result
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION comparison_deferred_check();
CREATE CONSTRAINT TRIGGER comparison_input_complete AFTER INSERT OR DELETE ON match_input_skill
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION comparison_deferred_check();
CREATE CONSTRAINT TRIGGER comparison_outcome_complete AFTER INSERT OR DELETE ON match_skill_result
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION comparison_deferred_check();
CREATE CONSTRAINT TRIGGER comparison_recommendation_complete AFTER INSERT OR DELETE ON recommendation
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION comparison_deferred_check();
"""

REVERSE = """
DROP TRIGGER comparison_recommendation_complete ON recommendation;
DROP TRIGGER comparison_outcome_complete ON match_skill_result;
DROP TRIGGER comparison_input_complete ON match_input_skill;
DROP TRIGGER comparison_result_complete ON match_result;
DROP FUNCTION comparison_deferred_check();
DROP TRIGGER comparison_recommendation_guard ON recommendation;
DROP TRIGGER comparison_outcome_guard ON match_skill_result;
DROP TRIGGER comparison_input_guard ON match_input_skill;
DROP FUNCTION comparison_child_guard();
DROP TRIGGER comparison_result_guard ON match_result;
DROP FUNCTION comparison_result_guard();
DROP FUNCTION comparison_assert_complete(uuid);
ALTER TABLE match_skill_result DROP CONSTRAINT outcome_input_fk;
ALTER TABLE match_skill_result DROP CONSTRAINT outcome_requirement_fk;
ALTER TABLE match_skill_result DROP CONSTRAINT outcome_match_target_fk;
ALTER TABLE recommendation DROP CONSTRAINT recommendation_version_kind_fk;
ALTER TABLE match_result DROP CONSTRAINT match_target_kind_fk;
"""


class Migration(migrations.Migration):
    dependencies = [("comparisons", "0001_initial"), ("reference", "0007_comparable_requirements")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
