"""Sign-in, POST-only sign-out, and owner-filtered student profile access."""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.shortcuts import get_object_or_404, render
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .forms import EmailAuthenticationForm
from .models import Student


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm

    def post(self, request, *args, **kwargs):
        # Local-demo throttle uses the direct peer address, never spoofable headers.
        # Deploy with a shared cache and an explicit trusted-proxy policy later.
        key = "login-failures:" + salted_hmac("login-peer", request.META.get("REMOTE_ADDR", "unknown")).hexdigest()
        limit = settings.LOGIN_FAILURE_LIMIT
        if cache.get(key, 0) >= limit:
            # Do not authenticate or run password hashing while throttled.
            form = self.authentication_form(request=request)
            response = self.render_to_response(
                self.get_context_data(form=form, throttled=True), status=429,
            )
            response["Retry-After"] = str(settings.LOGIN_FAILURE_WINDOW)
            return response
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            if not cache.add(key, 1, timeout=settings.LOGIN_FAILURE_WINDOW):
                try:
                    cache.incr(key)
                except ValueError:  # The counter expired between add and incr.
                    cache.add(key, 1, timeout=settings.LOGIN_FAILURE_WINDOW)
        return response


@never_cache
@login_required
@require_safe
def profile(request, student_id=None):
    # Always filter by the authenticated account, including explicit UUID routes.
    # Another student's record returns 404 rather than disclosing its existence.
    owned = Student.objects.filter(account=request.user)
    if student_id is not None:
        student = get_object_or_404(owned, student_id=student_id)
    else:
        student = owned.first()
    return render(request, "accounts/profile.html", {"student": student})
