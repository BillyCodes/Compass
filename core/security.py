"""Reusable authorization helpers (blueprint §5.3, §8).

Every private view goes through `student_required`, which:
  1. requires an authenticated session for an active account, and
  2. resolves the student from that session — never from a URL, form or body.
Record lookups then use `owned(...)`, which filters by the session's student
and returns 404 for anything else, so an unauthorized request cannot tell
whether another student's record exists.
"""
import hashlib
import logging
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.http import Http404, JsonResponse

log = logging.getLogger("compass.security")

LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60


def _student_for(request):
    user = request.user
    if not user.is_authenticated or not user.is_account_active():
        return None
    return getattr(user, "student", None)


def student_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        student = _student_for(request)
        if student is None:
            return redirect_to_login(request.get_full_path())
        request.student = student
        return view(request, *args, **kwargs)

    return wrapper


def api_student_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return api_error("unauthenticated", "Sign in to continue.", status=401)
        student = _student_for(request)
        if student is None:
            return api_error("forbidden", "This account can't access student data.", status=403)
        request.student = student
        return view(request, *args, **kwargs)

    return wrapper


def owned(queryset, request, **lookup):
    """Fetch one record that belongs to request.student, or 404."""
    obj = queryset.filter(student=request.student, **lookup).first()
    if obj is None:
        log.info("ownership denial: account=%s model=%s", request.user.pk, queryset.model.__name__)
        raise Http404
    return obj


# --- Login throttling ----------------------------------------------------------
def _throttle_key(email, ip):
    digest = hashlib.sha256(f"{(email or '').lower()}|{ip}".encode()).hexdigest()[:32]
    return f"login-fail:{digest}"


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def login_locked(email, ip):
    return cache.get(_throttle_key(email, ip), 0) >= LOGIN_MAX_FAILURES


def record_login_failure(email, ip):
    key = _throttle_key(email, ip)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, LOGIN_LOCK_SECONDS)
    log.info("login failure ip=%s", ip)   # never log the submitted email/password


def clear_login_failures(email, ip):
    cache.delete(_throttle_key(email, ip))


# --- Consistent JSON response shapes (blueprint §7.1) ---------------------------
def api_ok(data=None, status=200):
    return JsonResponse({"ok": True, "data": data}, status=status)


def api_error(code, message, status=400, fields=None):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return JsonResponse(body, status=status)
