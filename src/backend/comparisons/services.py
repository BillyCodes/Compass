"""Owner-scoped comparisons, frozen snapshots, and deterministic learning suggestions."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone

from reference.models import ContentItem, ContentSkill, ContentVersion
from reference.selectors import latest_available_learning
from skills.models import Skill, StudentSkill
from skills.services import _owned_student
from .models import MatchInputSkill, MatchResult, MatchSkillResult, Recommendation
from .scoring import ALGORITHM, Requirement, calculate


def list_matches(*, actor):
    return MatchResult.objects.filter(student=_owned_student(actor), finalized=True).select_related("target_version")


def get_match(*, actor, match_id):
    # Lookup and all child traversal begin from an owner-scoped result.
    return list_matches(actor=actor).prefetch_related("inputs__skill", "outcomes__skill").get(pk=match_id)


@transaction.atomic
def delete_match(*, actor, match_id):
    result = list_matches(actor=actor).select_for_update(of=("self",)).get(pk=match_id)
    result.delete()


def _recommendations(requirements, calculation):
    """Latest available edition per item, ranked by useful coverage of known gaps.

    Mandatory gap count first, weighted covered gap levels second, then UUID.
    Coverage above the student's level is capped at the target's required level.
    No claim is made that taking a course automatically awards this proficiency.
    """
    by_skill = {r.skill_id: r for r in requirements}
    gaps = {o.skill_id: o.gap for o in calculation.outcomes if o.status == "gap" and
            (by_skill[o.skill_id].mandatory or by_skill[o.skill_id].weight > 0)}
    if not gaps:
        return []
    useful_coverage = Q()
    for skill_id, gap in gaps.items():
        reported_level = by_skill[skill_id].required_level - gap
        useful_coverage |= Q(skill_id=skill_id, coverage_level__gt=reported_level)
    useful_mappings = ContentSkill.objects.filter(useful_coverage).order_by("skill_id")
    # Choose the latest available edition BEFORE testing usefulness/retired skills.
    # Filtering first would incorrectly fall back to an older, more useful edition.
    latest_ids = latest_available_learning().values("pk")
    versions = (ContentVersion.objects.filter(pk__in=Subquery(latest_ids))
                .filter(Exists(useful_mappings.filter(version_id=OuterRef("pk"))))
                .only("version_id", "kind")
                .prefetch_related(Prefetch("skill_mappings", queryset=useful_mappings)))
    candidates = []
    for version in versions:
        mappings = list(version.skill_mappings.all())
        covered = []
        for mapping in mappings:
            r = by_skill[mapping.skill_id]
            reported_level = r.required_level - gaps[r.skill_id]
            improvement = max(0, min(mapping.coverage_level, r.required_level) - reported_level)
            if improvement:
                covered.append((r, improvement))
        if not covered:
            continue
        mandatory_count = sum(r.mandatory for r, _ in covered)
        benefit = sum((r.weight * improvement for r, improvement in covered), Decimal(0))
        reason = {"rule": "mandatory_gaps_then_weighted_coverage_v1", "skills": [
            {"skill_id": str(r.skill_id), "mandatory": r.mandatory, "covered_gap_levels": improvement}
            for r, improvement in covered
        ]}
        candidates.append((mandatory_count, benefit, str(version.pk), version, reason))
    candidates.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [(row[3], row[4]) for row in candidates]


@transaction.atomic
def create_comparison(*, actor, target_version_id):
    student = _owned_student(actor)
    # Read only the item identity first, then lock item -> edition -> skills.
    # Proficiency services lock the same skill rows, so input updates serialize
    # against this snapshot, including insertion of a previously absent input.
    identity = ContentVersion.objects.only("item_id").get(pk=target_version_id)
    item = ContentItem.objects.select_for_update().get(pk=identity.item_id)
    version = ContentVersion.objects.select_for_update().get(pk=target_version_id)
    if (version.kind not in ("career", "job") or version.status != "published" or item.retired_at is not None):
        raise ValidationError("Choose an available published career or job version.")
    if version.__class__.objects.filter(pk=version.pk, details__expires_at__lte=timezone.now()).exists():
        raise ValidationError("This job has expired.")
    rows = list(version.requirements.order_by("skill_id"))
    skills = list(Skill.objects.select_for_update().filter(pk__in=[r.skill_id for r in rows]).order_by("skill_id"))
    if any(skill.status != Skill.Status.ACTIVE for skill in skills):
        raise ValidationError("The target contains a retired skill; choose an updated version.")
    levels = dict(StudentSkill.objects.filter(student=student, skill_id__in=[r.skill_id for r in rows]).values_list("skill_id", "proficiency_level"))
    requirements = [Requirement(r.skill_id, r.required_level, r.weight, r.mandatory) for r in rows]
    calculated = calculate(requirements, levels)
    result = MatchResult.objects.create(
        student=student, target_version=version, target_kind=version.kind, alg_version=ALGORITHM,
        score=calculated.score, mandatory_status=calculated.mandatory_status,
        reported_count=calculated.reported_count, relevant_count=calculated.relevant_count,
        is_provisional=calculated.is_provisional,
    )
    MatchInputSkill.objects.bulk_create([
        MatchInputSkill(match=result, skill_id=r.skill_id, level_used=levels.get(r.skill_id)) for r in requirements
    ])
    MatchSkillResult.objects.bulk_create([
        MatchSkillResult(match=result, target_version=version, skill_id=o.skill_id, status=o.status, gap=o.gap)
        for o in calculated.outcomes
    ])
    suggestions = _recommendations(requirements, calculated)
    Recommendation.objects.bulk_create([
        Recommendation(match=result, resource_version=version, resource_kind=version.kind, priority_rank=rank, reason=reason)
        for rank, (version, reason) in enumerate(suggestions, start=1)
    ])
    result.recommendation_count = len(suggestions)
    result.finalized = True
    result.save(update_fields=["recommendation_count", "finalized"])
    # Validate inside this service even when called within a larger transaction.
    with connection.cursor() as cursor:
        cursor.execute("SELECT comparison_assert_complete(%s)", [result.pk])
    return result
