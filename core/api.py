"""
JSON contract for Test Launch 01 (Engineering Blueprint §7).

| Operation        | Route                         | Authorization                      |
|------------------|-------------------------------|------------------------------------|
| CSRF token       | GET  /api/csrf                | anonymous                          |
| Register         | POST /api/register            | anonymous; field allowlist         |
| Login            | POST /api/login               | anonymous; active account          |
| Current student  | GET  /api/me  · PATCH /api/me | authenticated student; allowlist   |
| Dashboard        | GET  /api/dashboard-data      | authenticated student              |
| List skills      | GET  /api/skills              | authenticated student              |
| Own skills       | GET  /api/me/skills           | authenticated owner                |
| Update skill     | POST|PUT|DELETE /api/me/skills/<skill_id> | owner; allowlist        |
| Logout           | POST /api/logout              | authenticated session              |
| Career compare   | POST /api/comparisons · GET   | owner; published target            |

Every response is {"ok": true, "data": …} or {"ok": false, "error": {code, message, fields?}}.
The student is always resolved from the session. Bodies that try to set
role, student_id, account, status, score or similar fields are rejected.
"""
import json

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import RegisterForm
from .models import LEVEL_LABELS, JobPosting, Skill, StudentSkill
from .security import (
    api_error,
    api_ok,
    api_student_required,
    clear_login_failures,
    client_ip,
    login_locked,
    record_login_failure,
)
from .services import comparison, skillprint
from .views import GENERIC_LOGIN_ERROR, create_student_account, current_careers, visible_postings

REGISTER_FIELDS = {"name", "email", "major", "password", "password_confirm"}
LOGIN_FIELDS = {"email", "password"}
PROFILE_FIELDS = {"name", "major", "career_interests"}
SKILL_FIELDS = {"level", "evidence"}
COMPARE_FIELDS = {"career_id", "posting_id"}
MAX_BODY = 32 * 1024


def _body(request, allowed):
    """Parse a JSON object and enforce the field allowlist."""
    if len(request.body) > MAX_BODY:
        return None, api_error("too_large", "Request body is too large.", status=413)
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None, api_error("bad_json", "Send a JSON object.")
    if not isinstance(data, dict):
        return None, api_error("bad_json", "Send a JSON object.")
    extra = sorted(set(data) - allowed)
    if extra:
        return None, api_error(
            "unexpected_fields", "These fields can't be set here.", fields={k: "not allowed" for k in extra}
        )
    return data, None


def _student_payload(student):
    return {
        "name": student.name,
        "major": student.major,
        "career_interests": student.career_interests,
        "email": student.account.email,
    }


def _skill_payload(ss):
    return {
        "skill_id": ss.skill_id,
        "name": ss.skill.name,
        "category": ss.skill.category,
        "level": ss.level,
        "level_label": LEVEL_LABELS[ss.level],
        "evidence": ss.evidence,
        "source": ss.source,
    }


def _result_payload(r):
    return {
        "result_id": str(r.pk),
        "target": r.target_title,
        "target_type": r.target_type,
        "target_version": r.target_version,
        "algorithm_version": r.algorithm_version,
        "score": float(r.score),
        "status": r.status,
        "requirements_met": r.requirements_met,
        "requirements_total": r.requirements_total,
        "mandatory_met": r.mandatory_met,
        "mandatory_total": r.mandatory_total,
        "skills": r.detail,
        "created_at": r.created_at.isoformat(),
    }


# --- Anonymous ---------------------------------------------------------------
@require_GET
def csrf(request):
    return api_ok({"csrfToken": get_token(request)})


@require_POST
def register(request):
    data, err = _body(request, REGISTER_FIELDS)
    if err:
        return err
    data.setdefault("password_confirm", data.get("password"))
    form = RegisterForm(data)
    if not form.is_valid():
        fields = {k: " ".join(str(m) for m in v) for k, v in form.errors.items()}
        return api_error("validation", "Check the highlighted fields.", fields=fields)
    d = form.cleaned_data
    account, student = create_student_account(name=d["name"], email=d["email"], password=d["password"], major=d.get("major", ""))
    login(request, account, backend="django.contrib.auth.backends.ModelBackend")
    return api_ok(_student_payload(student), status=201)


@require_POST
def login_api(request):
    data, err = _body(request, LOGIN_FIELDS)
    if err:
        return err
    email = str(data.get("email", "")).strip().lower()[:254]
    password = str(data.get("password", ""))[:256]
    ip = client_ip(request)
    if login_locked(email, ip):
        return api_error("locked", "Too many attempts. Wait 15 minutes, then try again.", status=429)
    account = authenticate(request, email=email, password=password)
    if account is None:
        record_login_failure(email, ip)
        return api_error("invalid_credentials", GENERIC_LOGIN_ERROR, status=401)
    clear_login_failures(email, ip)
    login(request, account)
    student = getattr(account, "student", None)
    return api_ok(_student_payload(student) if student else {"email": account.email})


# --- Authenticated -----------------------------------------------------------
@require_POST
def logout_api(request):
    if not request.user.is_authenticated:
        return api_error("unauthenticated", "Sign in to continue.", status=401)
    logout(request)
    return api_ok({"signed_out": True})


@api_student_required
@require_http_methods(["GET", "PATCH"])
def me(request):
    student = request.student
    if request.method == "PATCH":
        data, err = _body(request, PROFILE_FIELDS)
        if err:
            return err
        limits = {"name": 80, "major": 80, "career_interests": 200}
        errors = {}
        for k, v in data.items():
            if not isinstance(v, str) or len(v.strip()) > limits[k] or (k == "name" and not v.strip()):
                errors[k] = f"Must be text up to {limits[k]} characters."
        if errors:
            return api_error("validation", "Check the highlighted fields.", fields=errors)
        for k, v in data.items():
            setattr(student, k, v.strip())
        student.save(update_fields=list(data.keys()) + ["updated_at"])
    return api_ok(_student_payload(student))


@api_student_required
@require_GET
def dashboard_data(request):
    student = request.student
    latest = skillprint.latest_readiness(student)
    return api_ok(
        {
            "student": _student_payload(student),
            "skillprint": skillprint.scores_for_student(student),
            "top_skills": [_skill_payload(s) for s in student.skills.select_related("skill")[:5]],
            "skill_count": student.skills.count(),
            "course_count": student.courses.count(),
            "latest_career_result": _result_payload(latest) if latest else None,
        }
    )


@api_student_required
@require_GET
def skills_catalog(request):
    return api_ok(
        [
            {"skill_id": s.skill_id, "name": s.name, "category": s.category, "description": s.description}
            for s in Skill.objects.all()
        ]
    )


@api_student_required
@require_GET
def my_skills(request):
    return api_ok([_skill_payload(s) for s in request.student.skills.select_related("skill")])


@api_student_required
@require_http_methods(["POST", "PUT", "DELETE"])
def my_skill(request, skill_id):
    skill = Skill.objects.filter(pk=skill_id).first()
    if skill is None:
        return api_error("not_found", "That skill isn't in the catalog.", status=404)
    if request.method == "DELETE":
        deleted, _ = StudentSkill.objects.filter(student=request.student, skill=skill).delete()
        if not deleted:
            return api_error("not_found", "That skill isn't on your Skillprint.", status=404)
        return api_ok({"removed": skill_id})
    data, err = _body(request, SKILL_FIELDS)
    if err:
        return err
    level = data.get("level")
    if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 5:
        return api_error("validation", "Check the highlighted fields.", fields={"level": "Whole number from 1 to 5."})
    evidence = data.get("evidence", "")
    if not isinstance(evidence, str) or len(evidence) > 240:
        return api_error("validation", "Check the highlighted fields.", fields={"evidence": "Text up to 240 characters."})
    ss, created = StudentSkill.objects.update_or_create(
        student=request.student,
        skill=skill,
        defaults={"level": level, "evidence": evidence.strip(), "source": StudentSkill.Source.SELF},
    )
    ss.refresh_from_db()
    return api_ok(_skill_payload(ss), status=201 if created else 200)


@api_student_required
@require_http_methods(["GET", "POST"])
def comparisons(request):
    if request.method == "GET":
        return api_ok([_result_payload(r) for r in request.student.results.all()[:20]])
    data, err = _body(request, COMPARE_FIELDS)
    if err:
        return err
    if bool(data.get("career_id")) == bool(data.get("posting_id")):
        return api_error("validation", "Send exactly one of career_id or posting_id.")
    if data.get("career_id"):
        career = current_careers().filter(pk=data["career_id"]).first() if str(data["career_id"]).isdigit() else None
        if career is None:
            return api_error("not_found", "That career target isn't available.", status=404)
        result = comparison.run_and_save(request.student, career=career)
    else:
        pid = data["posting_id"]
        posting = visible_postings(request.student).filter(pk=pid).first() if str(pid).isdigit() else None
        if posting is None:
            return api_error("not_found", "That posting isn't available.", status=404)
        result = comparison.run_and_save(request.student, posting=posting)
    return api_ok(_result_payload(result), status=201)
