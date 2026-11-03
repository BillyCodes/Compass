"""
COMPASS comparison engine — Programming Lead.

Pipeline (blueprint §9.2): load inputs → normalize → match → score → explain → persist.

    Score = 100 × Σ(weight_i × satisfaction_i) / Σ(weight_i)

Satisfaction uses an ORDINAL lookup on the gap (required − student) rather than
student/required division, because the 1–5 skill scale is a set of labels
(Aware … Advanced), not evenly spaced numbers.

        gap ≤ 0  (meets or exceeds)  → 1.00
        gap = 1                      → 0.60
        gap = 2                      → 0.30
        gap ≥ 3                      → 0.10
        skill missing                → 0.00

Mandatory requirements are reported separately ("3 of 4 mandatory met") so a
high weighted score can never hide a missing critical skill.

STATUS RULES (labels describe alignment; they never claim employment eligibility):
        Strong Match      score ≥ 75 and every mandatory requirement met
        Developing Match  score ≥ 45, or score ≥ 75 with a mandatory gap
        Early Stage       score < 45
        Not comparable    target has no usable requirements

Everything in this file is versioned by ALGORITHM_VERSION. Changing a number
here without bumping the version breaks the explainability of saved results.
These rules are PROPOSED for team approval (Decision Register: skill scale,
match formula/weights, mandatory-skill behavior, result terminology).

Complexity: student skills are indexed in a dict keyed by skill_id, so a
comparison is O(S + R) for S student skills and R requirements.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from core.models import LEVEL_LABELS, MatchResult

ALGORITHM_VERSION = "tl01-v1"

SATISFACTION_BY_GAP = {0: 1.0, 1: 0.6, 2: 0.3}
SATISFACTION_FAR = 0.1
STRONG_THRESHOLD = 75
DEVELOPING_THRESHOLD = 45

OUTCOME_ORDER = {"met": 0, "below": 1, "missing": 2}


@dataclass(frozen=True)
class Requirement:
    skill_id: str
    name: str
    category: str
    required_level: int
    weight: int
    mandatory: bool


def satisfaction(student_level, required_level):
    if student_level is None:
        return 0.0
    gap = required_level - student_level
    if gap <= 0:
        return 1.0
    return SATISFACTION_BY_GAP.get(gap, SATISFACTION_FAR)


def status_for(score, mandatory_met, mandatory_total, requirements_total):
    if requirements_total == 0:
        return "Not comparable"
    if score >= STRONG_THRESHOLD and mandatory_met == mandatory_total:
        return "Strong Match"
    if score >= DEVELOPING_THRESHOLD:  # includes a high score held back by a mandatory gap
        return "Developing Match"
    return "Early Stage"


def compare(student_levels, requirements):
    """Pure function. student_levels: {skill_id: level}. requirements: [Requirement].

    Duplicate requirement rows for the same skill are collapsed, keeping the
    strictest (highest level, highest weight, mandatory if any copy is).
    """
    collapsed = {}
    for r in requirements:
        prev = collapsed.get(r.skill_id)
        if prev is None:
            collapsed[r.skill_id] = r
        else:
            collapsed[r.skill_id] = Requirement(
                skill_id=r.skill_id,
                name=r.name,
                category=r.category,
                required_level=max(prev.required_level, r.required_level),
                weight=max(prev.weight, r.weight),
                mandatory=prev.mandatory or r.mandatory,
            )

    reqs = [r for r in collapsed.values() if 1 <= r.required_level <= 5 and r.weight > 0]
    total_weight = sum(r.weight for r in reqs)

    detail, earned = [], 0.0
    met = mand_met = mand_total = 0
    for r in reqs:
        have = student_levels.get(r.skill_id)
        sat = satisfaction(have, r.required_level)
        earned += r.weight * sat
        if have is None:
            outcome = "missing"
        elif have >= r.required_level:
            outcome = "met"
            met += 1
        else:
            outcome = "below"
        if r.mandatory:
            mand_total += 1
            if outcome == "met":
                mand_met += 1
        detail.append(
            {
                "skill_id": r.skill_id,
                "name": r.name,
                "category": r.category,
                "required_level": r.required_level,
                "required_label": LEVEL_LABELS[r.required_level],
                "student_level": have,
                "student_label": LEVEL_LABELS.get(have, "Not on your Skillprint") if have else "Not on your Skillprint",
                "weight": r.weight,
                "mandatory": r.mandatory,
                "satisfaction": round(sat, 2),
                "outcome": outcome,
            }
        )

    raw = (100.0 * earned / total_weight) if total_weight else 0.0
    score = Decimal(str(raw)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    detail.sort(key=lambda d: (OUTCOME_ORDER[d["outcome"]], not d["mandatory"], -d["weight"], d["name"]))

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "score": score,
        "status": status_for(float(score), mand_met, mand_total, len(reqs)),
        "requirements_met": met,
        "requirements_total": len(reqs),
        "mandatory_met": mand_met,
        "mandatory_total": mand_total,
        "detail": detail,
        "snapshot": {
            "skills": {r.skill_id: student_levels.get(r.skill_id) for r in reqs},
            "requirements": [
                {"skill_id": r.skill_id, "required_level": r.required_level, "weight": r.weight, "mandatory": r.mandatory}
                for r in sorted(reqs, key=lambda x: x.skill_id)
            ],
        },
    }


# ---------------------------------------------------------------------------
# Database-facing helpers
# ---------------------------------------------------------------------------
def student_levels(student):
    return dict(student.skills.values_list("skill_id", "level"))


def requirements_for_career(profile):
    return [
        Requirement(rq.skill_id, rq.skill.name, rq.skill.category, rq.required_level, rq.weight, rq.mandatory)
        for rq in profile.requirements.select_related("skill")
    ]


def requirements_for_posting(posting):
    return [
        Requirement(rq.skill_id, rq.skill.name, rq.skill.category, rq.required_level, rq.weight, rq.mandatory)
        for rq in posting.requirements.select_related("skill")
    ]


@transaction.atomic
def run_and_save(student, *, career=None, posting=None):
    """Compute from server-side inputs only and persist an explainable result."""
    if (career is None) == (posting is None):
        raise ValueError("Exactly one target is required")
    if career is not None:
        reqs = requirements_for_career(career)
        title, version, ttype = career.title, career.version, MatchResult.TargetType.CAREER
    else:
        reqs = requirements_for_posting(posting)
        title, version, ttype = f"{posting.title} — {posting.company}", posting.version, MatchResult.TargetType.POSTING

    out = compare(student_levels(student), reqs)
    return MatchResult.objects.create(
        student=student,
        target_type=ttype,
        career_profile=career,
        posting=posting,
        target_title=title[:180],
        target_version=version,
        algorithm_version=out["algorithm_version"],
        score=out["score"],
        status=out["status"],
        mandatory_met=out["mandatory_met"],
        mandatory_total=out["mandatory_total"],
        requirements_met=out["requirements_met"],
        requirements_total=out["requirements_total"],
        detail=out["detail"],
        input_snapshot=out["snapshot"],
    )


def group_detail(detail):
    groups = {"met": [], "below": [], "missing": []}
    for d in detail:
        groups[d["outcome"]].append(d)
    return groups
