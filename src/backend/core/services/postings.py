"""Turn a pasted job posting into structured requirements.

PROPOSED parsing rule (documented, versioned with the algorithm):
  * Skills found under a "required / minimum / basic qualifications / must have"
    heading are MANDATORY, required level 3 (Developing), weight 2.
  * Skills found under a "preferred / nice to have / bonus / plus" heading are
    optional, required level 3, weight 1.
  * Skills found anywhere else in the posting are optional, level 3, weight 1.
  * If the posting has no recognizable headings, every detected skill is
    treated as optional — the parser does not invent mandatory requirements.
"""
import re

from django.db import transaction

from core.models import JobPosting, PostingRequirement

from .skill_matcher import find_skills

_REQUIRED_HDR = re.compile(
    r"^\W*(required|requirements|minimum qualifications|basic qualifications|must[- ]haves?|what you('ll)? need|you have|qualifications)\b",
    re.IGNORECASE,
)
_PREFERRED_HDR = re.compile(
    r"^\W*(preferred|nice[- ]to[- ]haves?|bonus|pluses|plus|preferred qualifications|desired)\b",
    re.IGNORECASE,
)
_OTHER_HDR = re.compile(
    r"^\W*(about (us|the role|the team)|responsibilities|what you('ll)? do|benefits|perks|compensation|the role)\b",
    re.IGNORECASE,
)


def _sections(text):
    """Split into (kind, chunk) where kind is required|preferred|other."""
    kind = "other"
    out = {"required": [], "preferred": [], "other": []}
    saw_heading = False
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
    rest = find_skills(text)
    rows = {}
    for sid, hit in rest.items():
        rows[sid] = {"skill": hit.skill, "required_level": 3, "weight": 1, "mandatory": False}
    for sid, hit in pref.items():
        rows[sid] = {"skill": hit.skill, "required_level": 3, "weight": 1, "mandatory": False}
    for sid, hit in req.items():
        rows[sid] = {"skill": hit.skill, "required_level": 3, "weight": 2, "mandatory": True}
    return list(rows.values())


@transaction.atomic
def create_student_posting(student, title, company, description):
    rows = parse_requirements(description)
    posting = JobPosting.objects.create(
        owner=student,
        title=title[:100],
        company=company[:80],
        description=description,
        tags="Your posting",
    )
    PostingRequirement.objects.bulk_create(
        PostingRequirement(
            posting=posting,
            skill=r["skill"],
            required_level=r["required_level"],
            weight=r["weight"],
            mandatory=r["mandatory"],
        )
        for r in rows
    )
    return posting, rows
