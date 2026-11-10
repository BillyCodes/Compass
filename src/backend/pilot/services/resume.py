"""Resume import.

The uploaded file is read in memory, converted to text, scanned for catalog
skills, and discarded. Only the detected skills are kept, and nothing reaches
the student's Skillprint until the student reviews and confirms the levels.

Suggested level (documented rule): mentioned once → 2 (Beginner); mentioned
2+ times → 3 (Intermediate). Never higher: a resume mention is not proof of
proficiency. The student can raise or lower any level before saving.
"""
import io
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from pilot.models import ResumeImport
from skills.models import Skill, StudentSkill
from skills.services import _owned_student, set_student_skill
from .skill_matcher import find_skills
from .skillprint import category_key, save_snapshot

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_PDF_PAGES = 10
_EXPERIENCE_WORDS = re.compile(
    r"\b(built|developed|implemented|designed|deployed|maintained|led|created|engineered|automated|configured)\b", re.IGNORECASE)


class ResumeError(Exception):
    """A problem the student can fix (wrong type, too big, unreadable)."""


def _ext(name):
    name = (name or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def extract_text(uploaded):
    max_bytes = getattr(settings, "COMPASS_MAX_RESUME_BYTES", 2 * 1024 * 1024)
    max_chars = getattr(settings, "COMPASS_MAX_TEXT_CHARS", 20000)
    ext = _ext(uploaded.name)
    if ext not in ALLOWED_EXTENSIONS:
        raise ResumeError("Upload a PDF, Word (.docx), or plain-text (.txt) resume.")
    if uploaded.size > max_bytes:
        raise ResumeError("That file is larger than 2 MB. Export a smaller copy and try again.")
    data = uploaded.read(max_bytes + 1)
    try:
        if ext == ".pdf":
            if not data.startswith(b"%PDF"):
                raise ResumeError("That file doesn't look like a PDF.")
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ResumeError("That PDF is password-protected. Upload an unlocked copy.")
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])
        elif ext == ".docx":
            if not data.startswith(b"PK"):
                raise ResumeError("That file doesn't look like a Word document.")
            import docx
            document = docx.Document(io.BytesIO(data))
            parts = [p.text for p in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    parts.extend(cell.text for cell in row.cells)
            text = "\n".join(parts)
        else:
            text = data.decode("utf-8", errors="replace")
    except ResumeError:
        raise
    except Exception:
        raise ResumeError("We couldn't read that file. Try saving it again as PDF or .docx.") from None
    text = text[: max_chars * 2]
    if len(text.strip()) < 40:
        raise ResumeError("We couldn't find text in that file. If it's a scanned image, upload a text-based PDF or .docx.")
    return text


def detect_skills(text):
    suggestions = []
    for skill_id, hit in find_skills(text).items():
        suggestions.append({
            "skill_id": skill_id, "name": hit.skill.skill_name, "category": category_key(hit.skill.category) or "",
            "hits": hit.hits, "suggested_level": 2 if hit.hits == 1 else 3,
            "experience": any(_EXPERIENCE_WORDS.search(c) for c in hit.contexts),
            "context": hit.contexts[0] if hit.contexts else "",
        })
    suggestions.sort(key=lambda s: (-s["hits"], s["name"]))
    return suggestions


def create_import(*, actor, uploaded):
    """Read an upload and keep only the detected skills."""
    student = _owned_student(actor)
    text = extract_text(uploaded)
    return ResumeImport.objects.create(
        student=student, filename=uploaded.name[:120], char_count=len(text), detected=detect_skills(text))


def get_import(*, actor, import_id):
    return ResumeImport.objects.get(pk=import_id, student=_owned_student(actor))


def list_imports(*, actor, limit=5):
    return ResumeImport.objects.filter(student=_owned_student(actor))[:limit]


@transaction.atomic
def apply_import(*, actor, import_id, choices):
    """choices: {skill_id(str): level}. Only skills detected in this import are accepted."""
    student = _owned_student(actor)
    imp = ResumeImport.objects.select_for_update().get(pk=import_id, student=student)
    valid = {d["skill_id"] for d in imp.detected}
    applied = 0
    for skill_id, level in choices.items():
        if skill_id not in valid or type(level) is not int or not 1 <= level <= 5:
            continue
        try:
            set_student_skill(actor=actor, skill_id=skill_id, proficiency_level=level, evidence_text=f"Resume: {imp.filename}"[:240])
        except (ValidationError, Skill.DoesNotExist):
            continue  # retired or malformed skill: skip rather than fail the whole save
        applied += 1
    imp.applied = True
    imp.save(update_fields=["applied"])
    save_snapshot(actor=actor, label=f"Resume import · {imp.filename}")
    return applied


def current_levels(*, actor):
    return dict(StudentSkill.objects.filter(student=_owned_student(actor)).values_list("skill_id", "proficiency_level"))
