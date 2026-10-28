# Decisions this build made — team sign-off needed

The blueprint's Decision Register (§14) left several items OPEN. To ship a working build, this code picks one reasonable answer for each, labels it here, and keeps it in one place so it is easy to change. Nothing below is final until the team agrees.

| Decision (blueprint §14) | What this build does | Where to change it | Status |
|---|---|---|---|
| Python framework | **Django 6.1** (the Oct 22 plan's recommendation) | whole project | PROPOSED |
| Authentication approach | Local accounts, Django's PBKDF2 password hashing, server-side DB sessions, rotated on login, flushed on logout | `settings.py`, `views.login_view` | PROPOSED |
| Account / profile relationship | Separate `Account` (identity, status, role) and `Student` (academic profile), one-to-zero-or-one, opaque UUID `student_id` | `models.py` | PROPOSED (matches security recommendation) |
| Pilot registration fields | name, email, password, major (optional) | `forms.RegisterForm`, `api.REGISTER_FIELDS` | PROPOSED |
| Protected write for demo | Both: StudentSkill update and profile update | `views.py`, `api.py` | PROPOSED |
| Skill scale | 1–5 ordinal: Aware, Beginner, Developing, Proficient, Advanced | `models.SKILL_LEVELS` | PROPOSED |
| Match formula / weights | `100 × Σ(w × s) / Σw`, where s comes from a gap lookup: meets = 1.0, 1 short = 0.6, 2 short = 0.3, 3+ short = 0.1, missing = 0 | `services/comparison.py` | PROPOSED |
| Mandatory-skill behavior | Reported separately ("2 of 3 mandatory met"); a missing mandatory skill blocks "Strong Match" | `comparison.status_for` | PROPOSED |
| Result terminology | Strong Match (≥75 and all mandatory met) · Developing Match (≥45) · Early Stage (<45) · Not comparable. No "eligible" wording. | `comparison.status_for` | PROPOSED |
| Stretch comparison in TL01 | Included | — | Team checkpoint |

## Scope additions the team asked for beyond the blueprint

The blueprint lists file uploads, the full Skillprint, and Field Notes as out of scope for TL01. The team asked for them in this pilot, so they are built with these guardrails:

- **Resume upload**: PDF/.docx/.txt only, 2 MB cap, magic-byte check, parsed in memory and **never stored**. Only the detected skill list is kept. Suggested levels top out at Developing (3), because a resume mention isn't proof of proficiency, and the student confirms every level before anything is saved.
- **Pasted job postings**: stored privately per student; skills under "Requirements" become mandatory, skills under "Preferred" become optional, everything at required level 3. No external URLs are fetched.
- **Skillprint chart**: six categories; each score is the average of the student's three strongest levels in that category. Server-rendered SVG, no chart library.
- **Field Notes**: six sample notes written for the pilot, with fictional authors and companies, clearly labeled in the UI.
- **Save progress**: `ProgressSnapshot` rows; also auto-saved after a resume import.

## Versioning rule

`ALGORITHM_VERSION` (currently `tl01-v1`) is stored on every saved result along with the target version and the input snapshot. **If you change any number in `comparison.py`, bump the version.** Career profiles are versioned by `(slug, version)`; publish a new row instead of editing one that results already reference.

## Known limits of this pilot

- Login throttling uses Django's in-process cache, so it resets on restart and isn't shared across servers. Use Redis or database caching before any multi-server deploy.
- Resume skill detection is phrase matching against the 32-skill catalog. It won't find skills that aren't in the catalog or are described without their usual names.
- The course catalog uses illustrative course codes; the Database Lead should replace them with the real catalog.
