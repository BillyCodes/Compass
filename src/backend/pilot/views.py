"""Resume import, saved progress, and pasted-posting comparisons."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.security import student_required
from skills.models import ProficiencyLevel
from .forms import PostingForm, ResumeForm
from .models import ResumeImport, StudentPosting
from .services import postings, resume, skillprint
from .services.skillprint import CATEGORY_LABELS


@student_required
@require_http_methods(["GET", "POST"])
def resume_upload(request):
    form = ResumeForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    error = None
    if request.method == "POST":
        if form.is_valid():
            try:
                imp = resume.create_import(actor=request.user, uploaded=form.cleaned_data["resume"])
            except resume.ResumeError as exc:
                error = str(exc)
            else:
                return redirect("pilot:resume-review", import_id=imp.pk)
        else:
            error = "Choose a resume file to upload."
    return render(request, "core/resume_upload.html", {"active": "resume", "form": form, "error": error,
                                                       "past": resume.list_imports(actor=request.user)})


@student_required
@require_http_methods(["GET", "POST"])
def resume_review(request, import_id):
    try:
        imp = resume.get_import(actor=request.user, import_id=import_id)
    except ResumeImport.DoesNotExist:
        raise Http404 from None
    if request.method == "POST":
        choices = {}
        for d in imp.detected:
            sid = d["skill_id"]
            if request.POST.get(f"keep_{sid}") != "on":
                continue
            try:
                choices[sid] = int(request.POST.get(f"level_{sid}", d["suggested_level"]))
            except ValueError:
                continue
        applied = resume.apply_import(actor=request.user, import_id=imp.pk, choices=choices)
        messages.success(request, f"Saved {applied} skill{'s' if applied != 1 else ''} from your resume. Progress saved.")
        return redirect("core:dashboard")
    mine = {str(k): v for k, v in resume.current_levels(actor=request.user).items()}
    rows = [{**d, "current": mine.get(d["skill_id"]), "category_label": CATEGORY_LABELS.get(d["category"], "")} for d in imp.detected]
    levels = [(v, l) for v, l in ProficiencyLevel.choices if v >= 1]
    return render(request, "core/resume_review.html", {"active": "resume", "imp": imp, "rows": rows, "levels": levels})


@student_required
@require_POST
def save_progress(request):
    label = (request.POST.get("label") or "").strip()[:80] or f"Saved {timezone.localdate():%b %d, %Y}"
    skillprint.save_snapshot(actor=request.user, label=label)
    messages.success(request, "Progress saved. You'll see it on your Journey.")
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect("comparisons:journey")


@student_required
@require_POST
def posting_create(request):
    form = PostingForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            posting = postings.create_posting(actor=request.user, title=d["title"], company=d["company"], description=d["description"])
            match = postings.run_posting_match(actor=request.user, posting_id=posting.pk)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            return redirect("comparisons:detail", match_id=match.pk)
    from comparisons.views import render_compare
    return render_compare(request, form)


@student_required
@require_POST
def posting_run(request, posting_id):
    try:
        match = postings.run_posting_match(actor=request.user, posting_id=posting_id)
    except StudentPosting.DoesNotExist:
        raise Http404 from None
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("comparisons:compare")
    return redirect("comparisons:detail", match_id=match.pk)
