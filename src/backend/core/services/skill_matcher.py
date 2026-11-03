"""Find catalog skills mentioned in free text (resumes, job postings).

Matching is deterministic: each skill's name and aliases become case-insensitive
patterns bounded so that "Java" does not match inside "JavaScript" and "C"
does not match random letters. Very short aliases (<=2 chars) only match as
standalone tokens with exact case, e.g. "Go" or "R" written as a language.
"""
import re
from dataclasses import dataclass, field

from core.models import Skill

_BOUNDARY_L = r"(?<![A-Za-z0-9+#.])"
_BOUNDARY_R = r"(?![A-Za-z0-9+#])"


@dataclass
class SkillHit:
    skill: Skill
    hits: int = 0
    contexts: list = field(default_factory=list)


def _pattern_for(alias):
    escaped = re.escape(alias)
    if len(alias) <= 2:
        return re.compile(_BOUNDARY_L + escaped + _BOUNDARY_R)          # case-sensitive
    return re.compile(_BOUNDARY_L + escaped + _BOUNDARY_R, re.IGNORECASE)


_cache = {"key": None, "patterns": None}


def _compiled_catalog():
    skills = list(Skill.objects.all().order_by("skill_id"))
    key = tuple((s.skill_id, s.name, s.aliases) for s in skills)
    if _cache["key"] != key:
        _cache["key"] = key
        _cache["patterns"] = [(s, [_pattern_for(a) for a in s.alias_list()]) for s in skills]
    return _cache["patterns"]


def _snippet(text, start, end, width=60):
    a = max(0, start - width)
    b = min(len(text), end + width)
    s = text[a:b].replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def find_skills(text):
    """Return {skill_id: SkillHit} for every catalog skill found in text."""
    found = {}
    if not text:
        return found
    for skill, patterns in _compiled_catalog():
        spans = []
        for pat in patterns:
            for m in pat.finditer(text):
                spans.append((m.start(), m.end()))
        if not spans:
            continue
        spans.sort()
        # collapse overlapping matches from multiple aliases
        merged = []
        for s, e in spans:
            if merged and s < merged[-1][1]:
                continue
            merged.append((s, e))
        hit = SkillHit(skill=skill, hits=len(merged))
        hit.contexts = [_snippet(text, s, e) for s, e in merged[:2]]
        found[skill.skill_id] = hit
    return found
