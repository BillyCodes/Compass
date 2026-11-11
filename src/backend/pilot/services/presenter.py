"""Shape approved backend data for the Test Launch templates.

Pure presentation: nothing here writes data or changes how scores are computed.
Status labels are derived from the stored score and mandatory status.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Subquery
from reference.models import ContentVersion

from comparisons.scoring import Requirement, calculate
from reference.selectors import latest_available
from reference.services import available_content_versions
from skills.models import ProficiencyLevel

LEVELS = dict(ProficiencyLevel.choices)
STRONG, DEVELOPING = 75, 45
MANDATORY_LABELS = {"met": "Met", "not_met": "Not met", "undetermined": "Undetermined", "not_applicable": "Not applicable"}


def match_status(score, mandatory_status):
    score = float(score)
    if score >= STRONG and mandatory_status in ("met", "not_applicable"):
        return "Strong Match"
    return "Developing Match" if score >= DEVELOPING else "Early Stage"


# --- Field Notes -------------------------------------------------------------
def note_card(version):
    profile = getattr(version, "field_note", None)
    card = {"pk": version.pk, "headline": version.title, "body": version.body, "published_at": version.published_at,
            "author_name": "", "author_role": "", "author_org": "", "years_experience": None, "quote": "",
            "working_on": "", "learn_next": "", "is_sample": False, "initials": "C", "skills": []}
    if profile is not None:
        card.update(author_name=profile.author_name, author_role=profile.author_role, author_org=profile.author_org,
                    years_experience=profile.years_experience, quote=profile.quote, working_on=profile.working_on,
                    learn_next=profile.learn_next, is_sample=profile.is_sample, initials=profile.initials,
                    skills=list(profile.skills.all()))
    return card


def note_versions(*, skill_id=None):
    # Select the latest edition before applying tag filters or display ordering.
    latest = latest_available("insight").values("pk")
    versions = ContentVersion.objects.filter(pk__in=Subquery(latest)).select_related("field_note").prefetch_related("field_note__skills")
    if skill_id:
        versions = versions.filter(field_note__skills=skill_id)
    return versions.order_by("-published_at", "version_id")


def available_notes(*, skill_id=None, limit=None):
    versions = note_versions(skill_id=skill_id)
    if limit is not None:
        versions = versions[:limit]
    return [note_card(v) for v in versions]


# --- Result summaries --------------------------------------------------------
def _row(skill_id, name, level, required_level, mandatory, weight, status, gap):
    return {"skill_id": skill_id, "name": name, "level": level, "label": "Unreported" if level is None else LEVELS[level],
            "required_level": required_level, "required_label": LEVELS[required_level], "mandatory": mandatory,
            "weight": weight, "gap": gap, "status": status}


def sort_groups(groups):
    for rows in groups.values():
        rows.sort(key=lambda r: (not r["mandatory"], -Decimal(str(r["weight"])), r["name"]))
    return groups


def counts(groups):
    rows = [r for g in groups.values() for r in g]
    return {"requirements_met": len(groups["met"]), "requirements_total": len(rows),
            "mandatory_total": sum(r["mandatory"] for r in rows),
            "mandatory_met": sum(r["mandatory"] for r in groups["met"])}


def summary_for(*, title, subtitle, location, created_at, score, mandatory_status, reported_count, relevant_count,
                is_provisional, alg_version, version_label, groups, rerun_url, delete_url, private, company=""):
    return {"title": title, "subtitle": subtitle, "company": company or subtitle, "location": location,
            "created_at": created_at, "score": score, "status": match_status(score, mandatory_status),
            "mandatory_label": MANDATORY_LABELS[mandatory_status], "reported_count": reported_count,
            "relevant_count": relevant_count, "is_provisional": is_provisional, "alg_version": alg_version,
            "version_label": version_label, "rerun_url": rerun_url, "delete_url": delete_url, "private": private,
            **counts(groups)}


def live_job_matches(levels, limit=3):
    """Unsaved comparison against currently published job editions (dashboard only)."""
    out = []
    for version in latest_available("job").prefetch_related("requirements"):
        rows = list(version.requirements.all())
        try:
            calc = calculate([Requirement(r.skill_id, r.required_level, r.weight, r.mandatory) for r in rows], levels)
        except ValidationError:
            continue  # nothing reported that is relevant to this posting
        company = version.details.company.company_name if getattr(version, "details", None) and version.details.company else ""
        out.append({"pk": version.pk, "title": version.title, "company": company,
                    "location": version.details.location if getattr(version, "details", None) else "",
                    "score": calc.score, "status": match_status(calc.score, calc.mandatory_status),
                    "is_provisional": calc.is_provisional, "reported_count": calc.reported_count,
                    "relevant_count": calc.relevant_count, "mandatory_status": calc.mandatory_status,
                    "mandatory_label": MANDATORY_LABELS[calc.mandatory_status]})
    out.sort(key=lambda m: -m["score"])
    return out[:limit]


def reference_available(version_ids):
    """Which saved recommendation targets are still available (published, active skills)."""
    return set(available_content_versions().exclude(skill_mappings__skill__status="retired")
               .filter(pk__in=version_ids).values_list("pk", flat=True))


def reference_groups(result):
    """Outcome rows for a saved reference comparison, grouped by status."""
    levels = dict(result.inputs.values_list("skill_id", "level_used"))
    requirements = {r.skill_id: r for r in result.target_version.requirements.all()}
    groups = {"met": [], "gap": [], "unreported": []}
    for o in result.outcomes.all():
        r = requirements[o.skill_id]
        groups[o.status].append(_row(o.skill_id, o.skill.skill_name, levels[o.skill_id], r.required_level, r.mandatory, r.weight, o.status, o.gap))
    return sort_groups(groups)


def posting_groups(match):
    """Outcome rows for a saved private-posting comparison (frozen JSON detail)."""
    groups = {"met": [], "gap": [], "unreported": []}
    for d in match.detail:
        groups[d["status"]].append(_row(d["skill_id"], d["name"], d["level_used"], d["required_level"], d["mandatory"], d["weight"], d["status"], d["gap"]))
    return sort_groups(groups)


def next_mission(*, has_skills, latest, groups):
    if latest is None:
        if not has_skills:
            return {"title": "Start your Skillprint", "body": "Upload your resume or add three skills you've used in class or on a project.", "url": "pilot:resume-upload", "cta": "Upload resume"}
        return {"title": "Run your first comparison", "body": "Pick a career or a job posting and see which skills you already meet.", "url": "comparisons:compare", "cta": "Compare now"}
    todo = groups["gap"] + groups["unreported"]
    if not todo:
        return {"title": "Aim higher", "body": f"You meet every requirement for {latest['title']}. Compare against a more senior posting.", "url": "comparisons:compare", "cta": "Choose a new target"}
    g = sorted(todo, key=lambda r: (not r["mandatory"], r["status"] != "gap"))[0]
    verb = "Report your level in" if g["status"] == "unreported" else "Level up"
    return {"title": f"{verb} {g['name']}", "body": f"{latest['title']} asks for {g['name']} at {g['required_label']}." + (" It's a mandatory requirement." if g["mandatory"] else ""),
            "url": "comparisons:detail", "arg": latest["pk"], "cta": "See your route"}
