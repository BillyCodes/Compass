"""Sign-in, POST-only sign-out, and owner-filtered student profile access."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from core.security import student_required
from .forms import EmailAuthenticationForm, ProfileForm, RegistrationForm
from .models import Role, Student
from .permissions import has_role
from .services import create_student, update_student_profile


class EmailLoginView(LoginView):
    template_name = "core/auth_login.html"
    authentication_form = EmailAuthenticationForm

    def get_success_url(self):
        target = self.get_redirect_url()
        if target:
            return target
        if has_role(self.request.user, Role.Name.STUDENT) and Student.objects.filter(account=self.request.user).exists():
            return reverse("core:dashboard")
        return reverse("accounts:profile")

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
    request.student = student
    return render(request, "core/profile.html", {"student": student, "active": "profile"})


@never_cache
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            student = create_student(email=data["email"], password=data["password"], display_name=data["name"], major=data["major"])
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
            if constraint not in ("account_email_ci_unique", "account_login_email_key"):
                raise
            form.add_error("email", "An account with this email already exists.")
        else:
            login(request, student.account, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("core:onboarding")
    return render(request, "core/auth_register.html", {"form": form})


@student_required
@require_http_methods(["GET", "POST"])
def edit_profile(request):
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.student)
    if request.method == "POST" and form.is_valid():
        try:
            request.student = update_student_profile(actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    return render(request, "core/profile.html", {"active": "profile", "student": request.student, "form": form})
