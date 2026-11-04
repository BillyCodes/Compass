"""HTTP access checks delegate student identity to the backend ownership service."""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from skills.services import _owned_student


def student_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request.student = _owned_student(request.user)
        return view(request, *args, **kwargs)
    return never_cache(login_required(wrapped))
