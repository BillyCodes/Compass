"""Skillprint: six category scores, the radar chart, and saved-progress snapshots.

Category score (0–100) = average of the student's (up to) three strongest reported
skill levels in that category, scaled so level 5 = 100. Slots with no skill are not
counted, so one Expert skill scores 100 and one Beginner skill scores 40. A category
with no skills scores 0.
"""
import math

from django.utils.html import escape

from comparisons.models import MatchResult
from skills.models import StudentSkill
from skills.services import _owned_student
from pilot.models import ProgressSnapshot

# (key, label) in radar order. Skill.category is free text; labels/keys both resolve.
CATEGORIES = [
    ("programming", "Programming"), ("data", "Data"), ("systems", "Systems"),
    ("security", "Cybersecurity"), ("professional", "Communication"), ("cloud", "Cloud / Tools"),
]
CATEGORY_LABELS = dict(CATEGORIES)
_LOOKUP = {**{k: k for k, _ in CATEGORIES}, **{label.lower(): k for k, label in CATEGORIES}}
_LOOKUP.update({"database": "data", "databases": "data"})
TOP_N = 3


def category_key(text):
    return _LOOKUP.get((text or "").strip().lower())


def category_scores(levels_by_category):
    scores = {}
    for key, _ in CATEGORIES:
        # Average of the student's strongest reported skills in the category (no padding),
        # so level 0..5 maps cleanly to 0, 20, 40, 60, 80, 100.
        levels = sorted(levels_by_category.get(key, []), reverse=True)[:TOP_N]
        scores[key] = round(sum(levels) / len(levels) / 5 * 100, 1) if levels else 0.0
    return scores


def _scores_for_levels(levels):
    buckets = {}
    for category, level in levels:
        key = category_key(category)
        if key:
            buckets.setdefault(key, []).append(level)
    return category_scores(buckets)


def scores_for_student(student):
    return _scores_for_levels(StudentSkill.objects.filter(student=student).values_list("skill__category", "proficiency_level"))


def latest_readiness(student):
    """Most recent saved career comparison, or None."""
    return (MatchResult.objects.filter(student=student, finalized=True, target_kind="career")
            .select_related("target_version").order_by("-created_at").first())


def current_levels(student):
    return {str(k): v for k, v in StudentSkill.objects.filter(student=student).values_list("skill_id", "proficiency_level")}


def save_snapshot(*, actor, label=""):
    student = _owned_student(actor)
    latest = latest_readiness(student)
    # One SQL read captures each level and its category together. Derive both
    # saved representations from these rows, even if proficiency changes next.
    rows = list(StudentSkill.objects.filter(student=student).values_list("skill_id", "skill__category", "proficiency_level"))
    return ProgressSnapshot.objects.create(
        student=student, label=(label or "")[:80], skills={str(skill_id): level for skill_id, _, level in rows},
        categories=_scores_for_levels((category, level) for _, category, level in rows), readiness=latest.score if latest else None,
    )


def last_snapshot(student):
    return ProgressSnapshot.objects.filter(student=student).order_by("-created_at").first()


def snapshot_is_current(snapshot):
    return snapshot is not None and snapshot.scoring_version == ProgressSnapshot.CURRENT_SCORING


def snapshot_delta(student):
    last = last_snapshot(student)
    if last is None:
        return None
    now = current_levels(student)
    improved = [sid for sid, lvl in now.items() if lvl > last.skills.get(sid, 0)]
    return {"since": last.created_at, "improved_count": len(improved)}


def radar_svg(scores, compare_scores=None, size=300, label_class="rl"):
    """Server-rendered SVG radar chart. Colors come from CSS classes so both themes work."""
    cats = [k for k, _ in CATEGORIES]
    n = len(cats)
    pad = 100
    w, h = size + pad * 2, size + 44
    cx, cy, r = w / 2, h / 2, size / 2 - 18

    def pt(i, frac):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + math.cos(ang) * r * frac, cy + math.sin(ang) * r * frac

    parts = [f'<svg class="radar" viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="Skillprint radar chart">']
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, ring) for i in range(n)))
        parts.append(f'<polygon class="radar-grid" points="{pts}"/>')
    for i in range(n):
        x, y = pt(i, 1.0)
        parts.append(f'<line class="radar-axis" x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}"/>')

    def shape(vals, cls):
        # Drawing only: values are floored at 3% of the radius so an all-zero profile
        # still renders a visible shape. Tooltips and page text show the true score.
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, max(vals.get(c, 0), 3) / 100) for i, c in enumerate(cats)))
        return f'<polygon class="{cls}" points="{pts}"/>'

    if compare_scores:
        parts.append(shape(compare_scores, "radar-prev"))
    parts.append(shape(scores, "radar-area"))
    for i, c in enumerate(cats):
        x, y = pt(i, max(scores.get(c, 0), 3) / 100)
        parts.append(f'<circle class="radar-dot" cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{escape(CATEGORY_LABELS[c])}: {scores.get(c, 0):.0f}</title></circle>')
    for i, c in enumerate(cats):
        x, y = pt(i, 1.17)
        anchor = "end" if x < cx - 10 else ("start" if x > cx + 10 else "middle")
        dy = 4 if abs(y - cy) < r * 0.6 else (0 if y < cy else 10)
        parts.append(f'<text class="{label_class}" x="{x:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}">{escape(CATEGORY_LABELS[c])}</text>')
    parts.append("</svg>")
    return "".join(parts)
