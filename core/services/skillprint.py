"""Skillprint: the student's capability profile as six category scores + a radar chart.

Category score (0–100) = average of the student's three strongest skill levels
in that category, with empty slots counted as 0, scaled so 5 = 100.
Example: Data skills at levels 4 and 3 → (4 + 3 + 0) / 3 = 2.33 → 46.7.
Taking the top three rewards depth without penalizing a student for catalog
skills they never claimed.
"""
import math

from django.utils.html import escape

from core.models import ProgressSnapshot, SkillCategory

CATEGORY_ORDER = [
    SkillCategory.PROGRAMMING,
    SkillCategory.DATA,
    SkillCategory.SYSTEMS,
    SkillCategory.SECURITY,
    SkillCategory.PROFESSIONAL,
    SkillCategory.CLOUD,
]
TOP_N = 3


def category_scores(levels_by_category):
    """levels_by_category: {category: [levels]} → {category: float 0–100}."""
    scores = {}
    for cat in CATEGORY_ORDER:
        levels = sorted(levels_by_category.get(cat.value, []), reverse=True)[:TOP_N]
        levels += [0] * (TOP_N - len(levels))
        scores[cat.value] = round(sum(levels) / TOP_N / 5 * 100, 1)
    return scores


def scores_for_student(student):
    buckets = {}
    for skill_id, cat, level in student.skills.values_list("skill_id", "skill__category", "level"):
        buckets.setdefault(cat, []).append(level)
    return category_scores(buckets)


def latest_readiness(student):
    latest = student.results.filter(target_type="career").order_by("-created_at").first()
    return latest


def save_snapshot(student, label=""):
    levels = dict(student.skills.values_list("skill_id", "level"))
    latest = latest_readiness(student)
    return ProgressSnapshot.objects.create(
        student=student,
        label=label[:80],
        skills=levels,
        categories=scores_for_student(student),
        readiness=latest.score if latest else None,
    )


def snapshot_delta(student):
    """Compare current Skillprint with the most recent saved snapshot."""
    last = student.snapshots.order_by("-created_at").first()
    if last is None:
        return None
    now = dict(student.skills.values_list("skill_id", "level"))
    improved = sorted(sid for sid, lvl in now.items() if lvl > last.skills.get(sid, 0))
    return {"since": last.created_at, "improved": improved, "improved_count": len(improved)}


def radar_svg(scores, compare_scores=None, size=300, label_class="rl"):
    """Server-rendered SVG radar chart. Colors come from CSS classes so both themes work."""
    labels = dict(SkillCategory.choices)
    cats = [c.value for c in CATEGORY_ORDER]
    n = len(cats)
    pad = 100
    w = size + pad * 2
    h = size + 44
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
        pts = " ".join(
            f"{x:.1f},{y:.1f}" for x, y in (pt(i, max(vals.get(c, 0), 3) / 100) for i, c in enumerate(cats))
        )
        return f'<polygon class="{cls}" points="{pts}"/>'

    if compare_scores:
        parts.append(shape(compare_scores, "radar-prev"))
    parts.append(shape(scores, "radar-area"))
    for i, c in enumerate(cats):
        x, y = pt(i, max(scores.get(c, 0), 3) / 100)
        parts.append(f'<circle class="radar-dot" cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{escape(labels[c])}: {scores.get(c, 0):.0f}</title></circle>')
    for i, c in enumerate(cats):
        x, y = pt(i, 1.17)
        anchor = "middle"
        if x < cx - 10:
            anchor = "end"
        elif x > cx + 10:
            anchor = "start"
        dy = 4 if abs(y - cy) < r * 0.6 else (0 if y < cy else 10)
        parts.append(
            f'<text class="{label_class}" x="{x:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}">{escape(labels[c])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
