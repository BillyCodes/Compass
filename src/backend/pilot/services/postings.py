"""Pasted job postings and their comparisons (private to the student).

Parsing rule (documented, deterministic):
  * Skills under a "required / minimum / basic qualifications / must have"
    heading are MANDATORY, required level 3, weight 2.
  * Skills under a "preferred / nice to have / bonus" heading are optional,
    level 3, weight 1. Skills found elsewhere are optional, level 3, weight 1.
  * With no recognizable headings, every detected skill is optional: the parser
    never invents mandatory requirements.
Scoring reuses the approved weighted_skill_match_v1 calculation unchanged.
"""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from comparisons.scoring import ALGORITHM, Requirement, calculate
from pilot.models import PostingMatch, StudentPosting, StudentPostingRequirement
from skills.models import Skill, StudentSkill
from skills.services import _owned_student
from .skill_matcher import find_skills

_REQUIRED_HDR = re.compile(r"^\W*(required|requirements|minimum qualifications|basic qualifications|must[- ]haves?|what you('ll)? need|you have|qualifications)\b", re.IGNORECASE)
_PREFERRED_HDR = re.compile(r"^\W*(preferred|nice[- ]to[- ]haves?|bonus|pluses|plus|preferred qualifications|desired)\b", re.IGNORECASE)
_OTHER_HDR = re.compile(r"^\W*(about (us|the role|the team)|responsibilities|what you('ll)? do|benefits|perks|compensation|the role)\b", re.IGNORECASE)
MAX_POSTINGS_SHOWN = 6


def _sections(text):
    kind, saw_heading = "other", False
    out = {"required": [], "preferred": [], "other": []}
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) < 60:
            if _PREFERRED_HDR.match(stripped):
                kind, saw_heading = "preferred", True
            elif _REQUIRED_HDR.match(stripped):
                kind, saw_heading = "required", True
            elif _OTHER_HDR.match(stripped):
                kind, saw_heading = "other", True
        out[kind].append(line)
    return {k: "\n".join(v) for k, v in out.items()}, saw_heading


def parse_requirements(text):
    sections, saw_heading = _sections(text)
    req = find_skills(sections["required"]) if saw_heading else {}
    pref = find_skills(sections["preferred"]) if saw_heading else {}
    rows = {sid: (hit.skill, 1, False) for sid, hit in find_skills(text).items()}
    rows.update({sid: (hit.skill, 1, False) for sid, hit in pref.items()})
    rows.update({sid: (hit.skill, 2, True) for sid, hit in req.items()})
    return [{"skill": skill, "required_level": 3, "weight": Decimal(weight), "mandatory": mandatory}
            for skill, weight, mandatory in rows.values()]


@transaction.atomic
def create_posting(*, actor, title, company, description):
    student = _owned_student(actor)
    if not all(isinstance(v, str) for v in (title, company, description)):
        raise ValidationError("Use plain text.")
    title, company, description = title.strip()[:100], company.strip()[:80], description.strip()[:20000]
    rows = parse_requirements(description)
    if not rows:
        raise ValidationError("We couldn't find any skills from the Compass catalog in that posting. Check that you pasted the requirements section.")
    posting = StudentPosting.objects.create(student=student, title=title, company=company, description=description)
    StudentPostingRequirement.objects.bulk_create(
        StudentPostingRequirement(posting=posting, skill=r["skill"], required_level=r["required_level"], weight=r["weight"], mandatory=r["mandatory"])
        for r in rows)
    return posting


def list_postings(*, actor):
    return StudentPosting.objects.filter(student=_owned_student(actor)).prefetch_related("requirements")


def get_posting(*, actor, posting_id):
    return StudentPosting.objects.get(pk=posting_id, student=_owned_student(actor))


@transaction.atomic
def run_posting_match(*, actor, posting_id):
    student = _owned_student(actor)
    posting = StudentPosting.objects.get(pk=posting_id, student=student)
    rows = list(posting.requirements.select_related("skill").order_by("skill_id"))
    # Lock skills in a stable order, matching the reference-comparison convention.
    skills = {s.pk: s for s in Skill.objects.select_for_update().filter(pk__in=[r.skill_id for r in rows]).order_by("skill_id")}
    rows = [r for r in rows if skills[r.skill_id].status == Skill.Status.ACTIVE]
    if not rows:
        raise ValidationError("This posting no longer contains any active catalog skills.")
    levels = dict(StudentSkill.objects.filter(student=student, skill_id__in=[r.skill_id for r in rows]).values_list("skill_id", "proficiency_level"))
    requirements = [Requirement(r.skill_id, r.required_level, r.weight, r.mandatory) for r in rows]
    calc = calculate(requirements, levels)
    by_skill = {r.skill_id: r for r in rows}
    detail = [{"skill_id": str(o.skill_id), "name": by_skill[o.skill_id].skill.skill_name,
               "required_level": by_skill[o.skill_id].required_level, "level_used": levels.get(o.skill_id),
               "weight": str(by_skill[o.skill_id].weight), "mandatory": by_skill[o.skill_id].mandatory,
               "status": o.status, "gap": o.gap} for o in calc.outcomes]
    return PostingMatch.objects.create(
        student=student, posting=posting, target_title=posting.title, target_company=posting.company, alg_version=ALGORITHM,
        score=calc.score, mandatory_status=calc.mandatory_status, reported_count=calc.reported_count,
        relevant_count=calc.relevant_count, is_provisional=calc.is_provisional, detail=detail)


def list_posting_matches(*, actor):
    return PostingMatch.objects.filter(student=_owned_student(actor))


def get_posting_match(*, actor, match_id):
    return list_posting_matches(actor=actor).get(pk=match_id)


@transaction.atomic
def delete_posting_match(*, actor, match_id):
    list_posting_matches(actor=actor).get(pk=match_id).delete()
