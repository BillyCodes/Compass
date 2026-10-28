"""Page views for the COMPASS Test Launch 01 student journey."""
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CourseForm, LoginForm, PostingForm, ProfileForm, RegisterForm, ResumeForm, SkillForm
from .models import (
    LEVEL_LABELS,
    SKILL_LEVELS,
    Account,
    CareerProfile,
    CourseSkill,
    FieldNote,
    JobPosting,
    MatchResult,
    ResumeImport,
    Skill,
    SkillCategory,
    Student,
    StudentCourse,
    StudentSkill,
)
from .security import (
    clear_login_failures,
    client_ip,
    login_locked,
    owned,
    record_login_failure,
    student_required,
)
from .services import comparison, postings, resume, skillprint

log = logging.getLogger("compass.security")
GENERIC_LOGIN_ERROR = "That email and password don't match an active account."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def current_careers():
    """Latest published version of each career profile."""
    latest = (
        CareerProfile.objects.filter(is_published=True)
        .values("slug")
        .annotate(v=Max("version"))
    )
    q = Q(pk__in=[])
    for row in latest:
        q |= Q(slug=row["slug"], version=row["v"])
    return CareerProfile.objects.filter(q, is_published=True).prefetch_related("requirements")


def visible_postings(student):
    return JobPosting.objects.filter(Q(owner__isnull=True) | Q(owner=student))


def create_student_account(*, name, email, password, major=""):
    """Account + linked student profile in one transaction (blueprint §5.1)."""
    with transaction.atomic():
        account = Account.objects.create_user(email=email, password=password)
        student = Student.objects.create(account=account, name=name, major=major)
    return account, student


def route_for(skill_ids):
    """Next-step resources for a set of gap skills: courses that build them and
    Field Notes that discuss them."""
    courses = {}
    for cs in CourseSkill.objects.filter(skill_id__in=skill_ids).select_related("course", "skill"):
        courses.setdefault(cs.skill_id, []).append(cs.course)
    notes = {}
    for note in FieldNote.objects.filter(skills__skill_id__in=skill_ids).distinct().prefetch_related("skills"):
        for s in note.skills.all():
            if s.skill_id in skill_ids:
                notes.setdefault(s.skill_id, []).append(note)
    return courses, notes


def next_mission(student, latest):
    if latest is None:
        if not student.skills.exists():
            return {
                "title": "Start your Skillprint",
                "body": "Upload your resume or add three skills you've used in class or on a project.",
                "url": "resume_upload",
                "cta": "Upload resume",
            }
        return {
            "title": "Run your first comparison",
            "body": "Pick a career or a job posting and see which skills you already meet.",
            "url": "compare",
            "cta": "Compare now",
        }
    gaps = [d for d in latest.detail if d["outcome"] != "met"]
    if not gaps:
        return {
            "title": "Aim higher",
            "body": f"You meet every requirement for {latest.target_title}. Compare against a more senior posting.",
            "url": "compare",
            "cta": "Choose a new target",
        }
    g = gaps[0]
    verb = "Learn" if g["outcome"] == "missing" else "Level up"
    return {
        "title": f"{verb} {g['name']}",
        "body": (
            f"{latest.target_title} asks for {g['name']} at {g['required_label']}."
            + (" It's a mandatory requirement." if g["mandatory"] else "")
        ),
        "url": "result_detail",
        "arg": latest.pk,
        "cta": "See your route",
    }


# ---------------------------------------------------------------------------
# Public pages and authentication
# ---------------------------------------------------------------------------
def home(request):
    notes = FieldNote.objects.all()[:3]
    example = {"programming": 80, "data": 66, "systems": 58, "security": 40, "professional": 72, "cloud": 46}
    return render(request, "core/home.html", {"notes": notes, "radar": skillprint.radar_svg(example)})


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        account, _ = create_student_account(
            name=d["name"], email=d["email"], password=d["password"], major=d.get("major", "")
        )
        login(request, account, backend="django.contrib.auth.backends.ModelBackend")
        log.info("account created id=%s", account.pk)
        messages.success(request, "Welcome to COMPASS. Let's build your Skillprint.")
        return redirect("onboarding")
    return render(request, "core/auth_register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        ip = client_ip(request)
        if login_locked(email, ip):
            error = "Too many attempts. Wait 15 minutes, then try again."
        else:
            account = authenticate(request, email=email, password=form.cleaned_data["password"])
            if account is None:
                record_login_failure(email, ip)
                error = GENERIC_LOGIN_ERROR
            else:
                clear_login_failures(email, ip)
                login(request, account)  # rotates the session key
                nxt = request.GET.get("next", "")
                if nxt.startswith("/") and not nxt.startswith("//"):
                    return redirect(nxt)
                return redirect("dashboard")
    elif request.method == "POST":
        error = GENERIC_LOGIN_ERROR
    return render(request, "core/auth_login.html", {"form": form, "error": error})


@require_POST
def logout_view(request):
    logout(request)  # flushes the server-side session; the old cookie is now worthless
    messages.info(request, "You're signed out.")
    return redirect("home")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@student_required
def onboarding(request):
    return render(request, "core/onboarding.html", {"active": "dashboard"})


@student_required
def dashboard(request):
    student = request.student
    scores = skillprint.scores_for_student(student)
    my_skills = list(student.skills.select_related("skill"))
    latest = skillprint.latest_readiness(student)
    previous = None
    if latest:
        previous = (
            student.results.filter(target_type="career", career_profile__slug=latest.career_profile.slug)
            .exclude(pk=latest.pk)
            .order_by("-created_at")
            .first()
        )
    delta = skillprint.snapshot_delta(student)
    last_snap = student.snapshots.first()

    # Live (unsaved) check against sample postings: "opportunities that match you"
    levels = comparison.student_levels(student)
    matches = []
    for p in JobPosting.objects.filter(owner__isnull=True).prefetch_related("requirements__skill"):
        out = comparison.compare(levels, comparison.requirements_for_posting(p))
        if out["requirements_total"]:
            matches.append((p, out))
    matches.sort(key=lambda m: -m[1]["score"])
    strong = [m for m in matches if m[1]["status"] == "Strong Match"]

    gap_ids = [d["skill_id"] for d in (latest.detail if latest else []) if d["outcome"] != "met"]
    notes = list(FieldNote.objects.filter(skills__skill_id__in=gap_ids).distinct()[:2]) if gap_ids else []
    if len(notes) < 2:
        notes += list(FieldNote.objects.exclude(pk__in=[n.pk for n in notes])[: 2 - len(notes)])

    ctx = {
        "active": "dashboard",
        "today": timezone.localdate(),
        "radar": skillprint.radar_svg(scores, last_snap.categories if last_snap else None),
        "has_prev_shape": bool(last_snap),
        "scores": scores,
        "top_skills": my_skills[:5],
        "skill_count": len(my_skills),
        "latest": latest,
        "readiness_delta": (latest.score - previous.score) if (latest and previous) else None,
        "delta": delta,
        "course_count": student.courses.count(),
        "matches": matches[:3],
        "strong_count": len(strong),
        "mission": next_mission(student, latest),
        "notes": notes,
        "greeting": _greeting(),
    }
    return render(request, "core/dashboard.html", ctx)


def _greeting():
    h = timezone.localtime().hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")


# ---------------------------------------------------------------------------
# Skillprint (protected reads and writes)
# ---------------------------------------------------------------------------
@student_required
@require_http_methods(["GET", "POST"])
def my_skillprint(request):
    student = request.student
    form = SkillForm(request.POST or None, prefix="skill")
    course_form = CourseForm(prefix="course")
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        obj, created = StudentSkill.objects.update_or_create(
            student=student,
            skill=d["skill"],
            defaults={"level": d["level"], "evidence": d["evidence"], "source": StudentSkill.Source.SELF},
        )
        messages.success(request, f"{'Added' if created else 'Updated'} {obj.skill.name} at {LEVEL_LABELS[obj.level]}.")
        return redirect("skillprint")

    scores = skillprint.scores_for_student(student)
    by_cat = {}
    for ss in student.skills.select_related("skill"):
        by_cat.setdefault(ss.skill.category, []).append(ss)
    groups = [(c.value, c.label, scores[c.value], by_cat.get(c.value, [])) for c in skillprint.CATEGORY_ORDER]
    last_snap = student.snapshots.first()
    ctx = {
        "active": "skillprint",
        "form": form,
        "course_form": course_form,
        "groups": groups,
        "radar": skillprint.radar_svg(scores, last_snap.categories if last_snap else None),
        "last_snap": last_snap,
        "levels": SKILL_LEVELS,
        "courses": student.courses.select_related("course").order_by("-added_at"),
    }
    return render(request, "core/skillprint.html", ctx)


@student_required
@require_POST
def update_skill(request, skill_id):
    """Inline level change from the Skillprint list. Ownership comes from the session."""
    ss = owned(StudentSkill.objects.select_related("skill"), request, skill_id=skill_id)
    try:
        level = int(request.POST.get("level", ""))
    except ValueError:
        level = 0
    if not 1 <= level <= 5:
        messages.error(request, "Choose a level from 1 (Aware) to 5 (Advanced).")
        return redirect("skillprint")
    ss.level = level
    ss.save(update_fields=["level", "updated_at"])
    messages.success(request, f"{ss.skill.name} is now {LEVEL_LABELS[level]}.")
    return redirect("skillprint")


@student_required
@require_POST
def remove_skill(request, skill_id):
    ss = owned(StudentSkill.objects.select_related("skill"), request, skill_id=skill_id)
    name = ss.skill.name
    ss.delete()
    messages.info(request, f"Removed {name} from your Skillprint.")
    return redirect("skillprint")


@student_required
@require_POST
def add_course(request):
    """Adding a course records it and suggests the skills it covers at their coverage level.
    A course never lowers a level the student already set (completion ≠ proficiency)."""
    form = CourseForm(request.POST, prefix="course")
    if not form.is_valid():
        messages.error(request, "Choose a course from the list.")
        return redirect("skillprint")
    course = form.cleaned_data["course"]
    _, created = StudentCourse.objects.get_or_create(
        student=request.student, course=course, defaults={"term": form.cleaned_data["term"]}
    )
    added = 0
    for cs in CourseSkill.objects.filter(course=course).select_related("skill"):
        ss, made = StudentSkill.objects.get_or_create(
            student=request.student,
            skill=cs.skill,
            defaults={"level": cs.coverage_level, "source": StudentSkill.Source.COURSE, "evidence": f"Coursework: {course.course_code}"},
        )
        if made:
            added += 1
    if created:
        messages.success(request, f"Added {course.course_code}. {added} new skill{'s' if added != 1 else ''} from this course joined your Skillprint.")
    else:
        messages.info(request, f"{course.course_code} is already on your record.")
    return redirect("skillprint")


@student_required
@require_POST
def save_progress(request):
    label = (request.POST.get("label") or "").strip()[:80] or f"Saved {timezone.localdate():%b %d, %Y}"
    skillprint.save_snapshot(request.student, label)
    messages.success(request, "Progress saved. You'll see it on your Journey.")
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "journey")


# ---------------------------------------------------------------------------
# Skill Explorer
# ---------------------------------------------------------------------------
@student_required
def skill_explorer(request):
    cat = request.GET.get("category", "")
    query = (request.GET.get("q") or "").strip()[:60]
    valid = dict(SkillCategory.choices)
    qs = Skill.objects.annotate(
        postings=Count("postingrequirement", filter=Q(postingrequirement__posting__owner__isnull=True))
    ).prefetch_related("courses")
    if cat in valid:
        qs = qs.filter(category=cat)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(aliases__icontains=query) | Q(description__icontains=query))
    mine = dict(request.student.skills.values_list("skill_id", "level"))
    return render(
        request,
        "core/explorer.html",
        {"active": "explorer", "skills": qs, "categories": SkillCategory.choices, "current": cat, "mine": mine, "query": query},
    )


# ---------------------------------------------------------------------------
# Resume import
# ---------------------------------------------------------------------------
@student_required
@require_http_methods(["GET", "POST"])
def resume_upload(request):
    form = ResumeForm(request.POST or None, request.FILES or None)
    error = None
    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data["resume"]
        try:
            text = resume.extract_text(f)
        except resume.ResumeError as e:
            error = str(e)
        else:
            found = resume.detect_skills(text)
            imp = ResumeImport.objects.create(
                student=request.student, filename=f.name[:120], char_count=len(text), detected=found
            )
            return redirect("resume_review", pk=imp.pk)
    elif request.method == "POST":
        error = "Choose a resume file to upload."
    past = request.student.resume_imports.all()[:5]
    return render(request, "core/resume_upload.html", {"active": "resume", "form": form, "error": error, "past": past})


@student_required
@require_http_methods(["GET", "POST"])
def resume_review(request, pk):
    imp = owned(ResumeImport.objects, request, pk=pk)
    mine = dict(request.student.skills.values_list("skill_id", "level"))
    if request.method == "POST":
        valid_ids = {d["skill_id"] for d in imp.detected}
        applied = 0
        with transaction.atomic():
            for d in imp.detected:
                sid = d["skill_id"]
                if request.POST.get(f"keep_{sid}") != "on":
                    continue
                try:
                    level = int(request.POST.get(f"level_{sid}", d["suggested_level"]))
                except ValueError:
                    continue
                if sid not in valid_ids or not 1 <= level <= 5:
                    continue
                StudentSkill.objects.update_or_create(
                    student=request.student,
                    skill_id=sid,
                    defaults={"level": level, "source": StudentSkill.Source.RESUME, "evidence": f"Resume: {imp.filename}"[:240]},
                )
                applied += 1
            imp.applied = True
            imp.save(update_fields=["applied"])
            skillprint.save_snapshot(request.student, f"Resume import · {imp.filename}")
        messages.success(request, f"Saved {applied} skill{'s' if applied != 1 else ''} from your resume. Progress saved.")
        return redirect("dashboard")
    rows = []
    for d in imp.detected:
        rows.append({**d, "current": mine.get(d["skill_id"]), "category_label": dict(SkillCategory.choices).get(d["category"], "")})
    return render(request, "core/resume_review.html", {"active": "resume", "imp": imp, "rows": rows, "levels": SKILL_LEVELS})


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------
@student_required
@require_http_methods(["GET", "POST"])
def compare(request):
    form = PostingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        posting, rows = postings.create_student_posting(request.student, d["title"], d["company"], d["description"])
        if not rows:
            messages.error(
                request,
                "We couldn't find any skills from the COMPASS catalog in that posting. Check that you pasted the requirements section.",
            )
            posting.delete()
        else:
            result = comparison.run_and_save(request.student, posting=posting)
            return redirect("result_detail", pk=result.pk)
    ctx = {
        "active": "compare",
        "careers": current_careers(),
        "samples": JobPosting.objects.filter(owner__isnull=True).prefetch_related("requirements"),
        "mine": JobPosting.objects.filter(owner=request.student).prefetch_related("requirements")[:6],
        "form": form,
        "has_skills": request.student.skills.exists(),
    }
    return render(request, "core/compare.html", ctx)


@student_required
@require_POST
def run_career_compare(request, pk):
    career = get_object_or_404(current_careers(), pk=pk)
    result = comparison.run_and_save(request.student, career=career)
    return redirect("result_detail", pk=result.pk)


@student_required
@require_POST
def run_posting_compare(request, pk):
    posting = get_object_or_404(visible_postings(request.student), pk=pk)
    result = comparison.run_and_save(request.student, posting=posting)
    return redirect("result_detail", pk=result.pk)


@student_required
def result_detail(request, pk):
    result = owned(MatchResult.objects.select_related("career_profile", "posting"), request, pk=pk)
    groups = comparison.group_detail(result.detail)
    gap_ids = [d["skill_id"] for d in result.detail if d["outcome"] != "met"]
    courses, notes = route_for(gap_ids)
    route = []
    for d in groups["missing"] + groups["below"]:
        route.append({**d, "courses": courses.get(d["skill_id"], [])[:2], "notes": notes.get(d["skill_id"], [])[:1]})
    current_levels = comparison.student_levels(request.student)
    changed = any(current_levels.get(k) != v for k, v in result.input_snapshot["skills"].items())
    company = result.posting.company if result.posting else "COMPASS career profile"
    return render(
        request,
        "core/result.html",
        {
            "active": "compare",
            "r": result,
            "groups": groups,
            "route": route[:6],
            "changed_since": changed,
            "company": company,
            "ring": float(result.score),
        },
    )


# ---------------------------------------------------------------------------
# Journey (saved progress + history)
# ---------------------------------------------------------------------------
@student_required
def journey(request):
    student = request.student
    snaps = list(student.snapshots.all()[:12])
    results = student.results.all()[:12]
    labels = dict(SkillCategory.choices)
    timeline = []
    for i, s in enumerate(snaps):
        prev = snaps[i + 1] if i + 1 < len(snaps) else None
        changes = []
        if prev:
            for cat in s.categories:
                diff = round(s.categories[cat] - prev.categories.get(cat, 0), 1)
                if diff:
                    changes.append((labels.get(cat, cat), diff))
        timeline.append({"snap": s, "changes": changes, "skill_total": len(s.skills)})
    current = skillprint.scores_for_student(student)
    oldest = snaps[-1] if snaps else None
    return render(
        request,
        "core/journey.html",
        {
            "active": "journey",
            "timeline": timeline,
            "results": results,
            "radar": skillprint.radar_svg(current, oldest.categories if oldest else None),
            "oldest": oldest,
        },
    )


# ---------------------------------------------------------------------------
# Field Notes (pilot sample content)
# ---------------------------------------------------------------------------
@student_required
def field_notes(request):
    skill = request.GET.get("skill", "")
    notes = FieldNote.objects.prefetch_related("skills")
    if skill:
        notes = notes.filter(skills__skill_id=skill)
    tagged = Skill.objects.filter(field_notes__isnull=False).distinct().order_by("name")
    return render(
        request,
        "core/field_notes.html",
        {"active": "notes", "notes": notes, "tagged": tagged, "current": skill},
    )


@student_required
def field_note_detail(request, pk):
    note = get_object_or_404(FieldNote.objects.prefetch_related("skills"), pk=pk)
    mine = dict(request.student.skills.values_list("skill_id", "level"))
    more = FieldNote.objects.exclude(pk=note.pk)[:3]
    return render(request, "core/field_note_detail.html", {"active": "notes", "note": note, "mine": mine, "more": more})


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@student_required
@require_http_methods(["GET", "POST"])
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.student)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(request, "core/profile.html", {"active": "profile", "form": form})
