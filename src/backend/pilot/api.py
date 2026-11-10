"""JSON contract for the imported frontend, layered on the approved services.

| Operation        | Route                          | Authorization                    |
|------------------|--------------------------------|----------------------------------|
| CSRF token       | GET  /api/csrf                 | anonymous                        |
| Register         | POST /api/register             | anonymous; field allowlist       |
| Login / logout   | POST /api/login · /api/logout  | anonymous / session              |
| Current student  | GET · PATCH /api/me            | active student; allowlist        |
| Dashboard        | GET  /api/dashboard-data       | active student                   |
| Skill catalog    | GET  /api/skills               | active student                   |
| Own skills       | GET  /api/me/skills            | owner                            |
| Update / remove  | POST|PUT|DELETE /api/me/skills/<uuid> | owner; allowlist           |
| Comparisons      | GET · POST /api/comparisons    | owner; reviewed or private target|

Every response is {"ok": true, "data": ...} or {"ok": false, "error": {code, message, fields?}}.
The student always comes from the session; bodies that try to set any other
field (role, student_id, account, score, ...) are rejected. Mutations require
Django's CSRF token (fetch one from /api/csrf) and reuse the web login throttle.
"""
import json

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.forms import RegistrationForm
from accounts.models import Role, Student
from accounts.permissions import has_role
from accounts.services import create_student, update_student_profile
from comparisons.models import MatchResult
from comparisons.services import create_comparison, list_matches
from reference.models import ContentVersion
from reference.services import available_content_versions
from skills.models import ProficiencyLevel, Skill
from skills.services import _owned_student, list_student_courses, list_student_skills, remove_student_skill, set_student_skill
from .models import StudentPosting
from .services import postings, skillprint
from .services.presenter import match_status

MAX_BODY = 32 * 1024
REGISTER_FIELDS = {"name", "email", "major", "password", "password_confirm"}
LOGIN_FIELDS = {"email", "password"}
PROFILE_FIELDS = {"display_name", "major", "career_interests", "graduation_year"}
SKILL_FIELDS = {"level", "evidence"}
COMPARE_FIELDS = {"version_id", "posting_id"}
GENERIC_LOGIN_ERROR = "That email and password don't match an active account."


def ok(data=None, status=200):
    return JsonResponse({"ok": True, "data": data}, status=status)


def error(code, message, status=400, fields=None):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return JsonResponse(body, status=status)


def api_student(view):
    """Active student resolved from the session; never from the URL or body."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error("unauthenticated", "Sign in to continue.", status=401)
        if not has_role(request.user, Role.Name.STUDENT):
            return error("forbidden", "This account can't access student data.", status=403)
        try:
            request.student = _owned_student(request.user)
        except PermissionDenied:
            return error("forbidden", "This account can't access student data.", status=403)
        return view(request, *args, **kwargs)
    return never_cache(wrapper)


def _body(request, allowed):
    if len(request.body) > MAX_BODY:
        return None, error("too_large", "Request body is too large.", status=413)
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None, error("bad_json", "Send a JSON object.")
    if not isinstance(data, dict):
        return None, error("bad_json", "Send a JSON object.")
    extra = sorted(set(data) - allowed)
    if extra:
        return None, error("unexpected_fields", "These fields can't be set: " + ", ".join(extra), fields={f: "Not allowed." for f in extra})
    return data, None


def _validation(exc):
    if hasattr(exc, "error_dict"):
        fields = {k: " ".join(v) for k, v in exc.message_dict.items()}
        return error("invalid", "Check the highlighted fields.", status=422, fields=fields)
    return error("invalid", " ".join(exc.messages), status=422)


def _student_json(student, account):
    return {"student_id": str(student.student_id), "name": student.display_name, "email": account.login_email,
            "major": student.major, "career_interests": student.career_interests, "graduation_year": student.graduation_year}


def _skill_json(record):
    return {"skill_id": str(record.skill_id), "name": record.skill.skill_name, "category": record.skill.category,
            "level": record.proficiency_level, "level_label": ProficiencyLevel(record.proficiency_level).label,
            "evidence": record.evidence_text}


def _match_json(m):
    return {"id": str(m.pk), "target_id": str(m.target_version_id), "title": m.target_version.title, "target_kind": m.target_kind,
            "score": str(m.score), "status": match_status(m.score, m.mandatory_status), "mandatory_status": m.mandatory_status,
            "reported_count": m.reported_count, "relevant_count": m.relevant_count, "is_provisional": m.is_provisional,
            "algorithm_version": m.alg_version, "created_at": m.created_at.isoformat()}


def _throttle_key(request):
    # Same counter as the web sign-in view, so both entry points share one limit.
    return "login-failures:" + salted_hmac("login-peer", request.META.get("REMOTE_ADDR", "unknown")).hexdigest()


@require_GET
def csrf(request):
    return ok({"csrfToken": get_token(request)})


@require_POST
@never_cache
def register(request):
    if request.user.is_authenticated:
        return error("already_signed_in", "Sign out before creating another account.", status=409)
    data, err = _body(request, REGISTER_FIELDS)
    if err:
        return err
    form = RegistrationForm({k: data.get(k, "") for k in REGISTER_FIELDS})
    if not form.is_valid():
        return error("invalid", "Check the highlighted fields.", status=422,
                     fields={k: " ".join(v) for k, v in form.errors.items()})
    d = form.cleaned_data
    try:
        student = create_student(email=d["email"], password=d["password"], display_name=d["name"], major=d["major"])
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
        if constraint not in ("account_email_ci_unique", "account_login_email_key"):
            raise
        return error("invalid", "Check the highlighted fields.", status=422, fields={"email": "An account with this email already exists."})
    login(request, student.account, backend="django.contrib.auth.backends.ModelBackend")
    return ok(_student_json(student, student.account), status=201)


@require_POST
@never_cache
def login_api(request):
    data, err = _body(request, LOGIN_FIELDS)
    if err:
        return err
    key, limit = _throttle_key(request), settings.LOGIN_FAILURE_LIMIT
    if cache.get(key, 0) >= limit:
        response = error("throttled", "Too many attempts. Try again later.", status=429)
        response["Retry-After"] = str(settings.LOGIN_FAILURE_WINDOW)
        return response
    email, password = data.get("email"), data.get("password")
    account = authenticate(request, username=email.strip().lower(), password=password) if isinstance(email, str) and isinstance(password, str) else None
    if account is None:
        if not cache.add(key, 1, timeout=settings.LOGIN_FAILURE_WINDOW):
            try:
                cache.incr(key)
            except ValueError:
                cache.add(key, 1, timeout=settings.LOGIN_FAILURE_WINDOW)
        return error("invalid_credentials", GENERIC_LOGIN_ERROR, status=401)
    login(request, account)  # rotates the session key
    student = Student.objects.filter(account=account).first()
    return ok(_student_json(student, account) if student else {"email": account.login_email})


@require_POST
def logout_api(request):
    logout(request)
    return ok()


@api_student
@require_http_methods(["GET", "PATCH"])
def me(request):
    if request.method == "PATCH":
        data, err = _body(request, PROFILE_FIELDS)
        if err:
            return err
        s = request.student
        merged = {"display_name": s.display_name, "major": s.major, "career_interests": s.career_interests,
                  "graduation_year": s.graduation_year, **data}
        try:
            for f in ("display_name", "major", "career_interests"):
                if not isinstance(merged[f], str):
                    raise ValidationError({f: "Use plain text."})
            year = merged["graduation_year"]
            if year is not None and (type(year) is not int or not 1900 <= year <= 2200):
                raise ValidationError({"graduation_year": "Use a four-digit year."})
            request.student = update_student_profile(actor=request.user, **{k: merged[k] for k in PROFILE_FIELDS})
        except ValidationError as exc:
            return _validation(exc)
    return ok(_student_json(request.student, request.user))


@api_student
@require_GET
def dashboard_data(request):
    student = request.student
    latest = skillprint.latest_readiness(student)
    return ok({"scores": skillprint.scores_for_student(student),
               "skill_count": list_student_skills(actor=request.user).count(),
               "course_count": list_student_courses(actor=request.user).count(),
               "latest": _match_json(latest) if latest else None,
               "delta": (lambda d: {"improved_count": d["improved_count"], "since": d["since"].isoformat()} if d else None)(skillprint.snapshot_delta(student))})


@api_student
@require_GET
def skills_catalog(request):
    return ok([{"skill_id": str(s.pk), "name": s.skill_name, "category": s.category}
               for s in Skill.objects.filter(status=Skill.Status.ACTIVE)])


@api_student
@require_GET
def my_skills(request):
    return ok([_skill_json(r) for r in list_student_skills(actor=request.user).order_by("-proficiency_level", "skill__skill_name")])


@api_student
@require_http_methods(["POST", "PUT", "DELETE"])
def my_skill(request, skill_id):
    if request.method == "DELETE":
        if not list_student_skills(actor=request.user).filter(skill_id=skill_id).exists():
            return error("not_found", "Not found.", status=404)  # same answer for unknown and foreign rows
        remove_student_skill(actor=request.user, skill_id=skill_id)
        return ok()
    data, err = _body(request, SKILL_FIELDS)
    if err:
        return err
    if "level" not in data:
        return error("invalid", "Provide a level from 0 to 5.", status=422, fields={"level": "Required."})
    existing = list_student_skills(actor=request.user).filter(skill_id=skill_id).first()
    evidence = data.get("evidence", existing.evidence_text if existing else "")
    try:
        record = set_student_skill(actor=request.user, skill_id=skill_id, proficiency_level=data["level"], evidence_text=evidence)
    except Skill.DoesNotExist:
        return error("not_found", "Not found.", status=404)
    except ValidationError as exc:
        return _validation(exc)
    record.skill = Skill.objects.get(pk=skill_id)
    return ok(_skill_json(record), status=200 if existing else 201)


@api_student
@require_http_methods(["GET", "POST"])
def comparisons(request):
    if request.method == "GET":
        return ok([_match_json(m) for m in list_matches(actor=request.user)])
    data, err = _body(request, COMPARE_FIELDS)
    if err:
        return err
    if len(data) != 1:
        return error("invalid", "Send exactly one of version_id or posting_id.", status=422)
    try:
        if "version_id" in data:
            version = available_content_versions().filter(kind__in=["career", "job"]).get(pk=data["version_id"])
            result = create_comparison(actor=request.user, target_version_id=version.pk)
            return ok(_match_json(MatchResult.objects.select_related("target_version").get(pk=result.pk)), status=201)
        posting = StudentPosting.objects.get(pk=data["posting_id"], student=request.student)
        match = postings.run_posting_match(actor=request.user, posting_id=posting.pk)
        return ok({"id": str(match.pk), "title": match.target_title, "score": str(match.score),
                   "status": match_status(match.score, match.mandatory_status), "mandatory_status": match.mandatory_status,
                   "is_provisional": match.is_provisional, "algorithm_version": match.alg_version}, status=201)
    except (ContentVersion.DoesNotExist, StudentPosting.DoesNotExist, ValueError):
        return error("not_found", "Not found.", status=404)
    except ValidationError as exc:
        return _validation(exc)
