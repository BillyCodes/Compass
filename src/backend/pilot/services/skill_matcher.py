"""Find active catalog skills mentioned in free text (resumes, job postings).

Matching is deterministic: each skill's name and aliases become case-insensitive
patterns bounded so that "Java" does not match inside "JavaScript". Very short
aliases (<=2 chars) only match as standalone tokens with exact case ("Go", "R").
"""
import re
from dataclasses import dataclass, field

from django.core.exceptions import ObjectDoesNotExist

from skills.models import Skill

_BOUNDARY_L = r"(?<![A-Za-z0-9+#.])"
_BOUNDARY_R = r"(?![A-Za-z0-9+#])"


@dataclass
class SkillHit:
    skill: Skill
    hits: int = 0
    contexts: list = field(default_factory=list)


def alias_list(skill):
    try:
        return skill.detail.alias_list()
    except ObjectDoesNotExist:
        return [skill.skill_name]


def _pattern_for(alias):
    escaped = re.escape(alias)
    flags = 0 if len(alias) <= 2 else re.IGNORECASE
    return re.compile(_BOUNDARY_L + escaped + _BOUNDARY_R, flags)


_cache = {"key": None, "patterns": None}


def _compiled_catalog():
    skills = list(Skill.objects.filter(status=Skill.Status.ACTIVE).select_related("detail").order_by("skill_name"))
    key = tuple((str(s.pk), s.skill_name, tuple(alias_list(s))) for s in skills)
    if _cache["key"] != key:
        _cache["key"] = key
        _cache["patterns"] = [(s, [_pattern_for(a) for a in alias_list(s)]) for s in skills]
    return _cache["patterns"]


def _snippet(text, start, end, width=60):
    a, b = max(0, start - width), min(len(text), end + width)
    s = re.sub(r"\s+", " ", text[a:b].replace("\n", " ")).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def find_skills(text):
    """Return {str(skill_id): SkillHit} for every active catalog skill found in text."""
    found = {}
    if not text:
        return found
    for skill, patterns in _compiled_catalog():
        spans = sorted((m.start(), m.end()) for pat in patterns for m in pat.finditer(text))
        if not spans:
            continue
        merged = []
        for s, e in spans:  # collapse overlapping matches from multiple aliases
            if merged and s < merged[-1][1]:
                continue
            merged.append((s, e))
        found[str(skill.pk)] = SkillHit(skill=skill, hits=len(merged), contexts=[_snippet(text, s, e) for s, e in merged[:2]])
    return found
