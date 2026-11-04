# Frontend integration with the approved backend

Implemented November 3, 2026 on `integration/frontend-main`. The imported Compass
visual design now uses the approved accounts, skills, reference, comparisons,
and auditing apps. No pilot models, migrations, alternate score engine, REST
framework, or new database tables were added.

## Connected screens and routes

| Screen | URL | Owner / behavior |
| --- | --- | --- |
| Landing page | `/` | `core:home`; reviewed insights and public account links |
| Register | `/accounts/register/` | Validated account/profile creation; student role only; initial assignment audited |
| Sign in / out | `/accounts/login/`, `/accounts/logout/` | Existing Django email authentication, throttle, safe next redirects, POST logout |
| Welcome | `/welcome/` | Student-role onboarding |
| Dashboard | `/dashboard/` | Owned proficiency, course count, latest saved comparison, reviewed jobs/insights |
| Owned profile | `/accounts/profile/`, `/accounts/students/<student_uuid>/` | Existing read-only ownership contract retained with the new design |
| Edit profile | `/accounts/profile/edit/` | Owned, allowlisted academic fields; no account/role changes |
| My Skillprint | `/skillprint/` | Existing proficiency services; explicit 0 and unreported remain distinct |
| Course selections | Forms on My Skillprint | Published course editions resolve to stable item UUIDs; selection never changes proficiency |
| Skill Explorer | `/explore/` | Active catalog search and actual backend categories |
| Compare | `/compare/` | Latest available career/job editions; no unreviewed or expired target listing |
| Run comparison | POST `/compare/<version_uuid>/` | Existing server-side scoring and atomic snapshot service |
| Saved result | `/results/<match_uuid>/` | Owned immutable inputs, outcomes, completeness, mandatory status, saved recommendation ranks |
| Your Journey | `/journey/` | Owned comparison history; POST-only whole-result deletion |
| Field Notes | `/field-notes/`, `/field-notes/<version_uuid>/` | Published `insight` editions; no invented professional author profiles |
| Learning detail | `/library/<version_uuid>/` | Available course/resource edition and validated HTTP(S) resource link |

Named URLs are namespaced by feature app. Existing `/accounts/` URLs remain
available. A successful student sign-in now defaults to the dashboard; other
accounts land on their owned account/profile page. Django still validates safe
`next` destinations. Nonstudent accounts do not receive student navigation/access.

The shared design lives in `core/base.html`, `core/app_base.html`, and the logo
partial. Feature views supply canonical model fields directly; imported pilot
field names and status/scoring explanations were replaced on connected pages.

## Business rules retained

- The scale is 0–5: None, Awareness, Beginner, Intermediate, Advanced, Expert.
- Student identity comes from the authenticated session and active student role.
  Private views use `core.security.student_required` and ownership-scoped services.
- Skill and course forms do not accept caller-selected student IDs or permissions.
  Inline edits/removal first establish ownership. Proficiency removal shares the
  skill-row locking convention used for input snapshots.
- Course selection is interest tracking, not completion or a proficiency award.
- Comparisons use `weighted_skill_match_v1` unchanged. Entirely unreported relevant
  inputs cannot save a result; partial input sets are explicitly provisional.
- Percentage, mandatory status, and completeness appear together. Unreported
  skills prompt input; saved recommendations target known gaps, mandatory first.
- History renders saved inputs, outcomes, target edition, recommendation rank,
  and explanation. It never recomputes a previous score or replaces its learning
  route with the current catalog. Withdrawn recommendations stay visible as
  historical entries without an actionable link.
- Reference visibility uses the existing published/retired/expiry policy. Private
  responses carry no-store headers; mutations require CSRF-protected POSTs.
- Registration validates duplicate email, password strength/confirmation, and
  preserves exact password characters. Account/profile/role creation and its
  audit event remain atomic through the existing service. Only the student role
  is granted; submitted staff/admin fields are ignored.

## Scope boundaries

Resume upload/review templates remain staged but are not routed or advertised.
A privacy-conscious import/review backend needs its own agreed behavior first.
Pasting private job postings and independent Skillprint progress snapshots also
remain separate features; this integration compares reviewed reference editions
and uses the existing comparison snapshots for Journey/history.

Field Notes uses actual published `insight` content, rather than adding the
pilot's professional/author models. No scores or category-readiness metrics were
invented to fill the old radar widget. The dashboard shows actual reported
proficiency and saved comparison information.

Maintenance/review/publication and audit services remain available on the backend;
new staff/admin management screens are not part of the imported student design.
No privileged accounts or content are automatically created/published.

The older project-level base/includes, account templates, layout CSS, and standalone
`frontend/` draft are now inactive for these connected screens. They are retained
as references for a separate cleanup after the team approves the integrated design.
Do not edit the standalone draft expecting changes to the Django interface.

## Run locally

From the repository root, using the existing `.env` and virtual environment:

```sh
docker compose up -d --wait db
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/`. Register a synthetic student or sign in through the
existing account route. Existing account passwords and database records are not
changed by this integration. The interactive `create_demo_accounts` command is
still available for a fresh development database and refuses to overwrite users.

Catalog, course, career/job, insight, and recommendation sections can be empty
until suitable reviewed content has been published. This is expected for the
existing empty reference tables. Populate data through validated catalog and
review/publication services; do not bypass independent approval to fill the UI.
No data reset or application-database migration was performed during verification.

## Verification

```sh
.venv/bin/python src/backend/manage.py test core accounts skills reference comparisons auditing
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
.venv/bin/python src/backend/manage.py check
```

The suite contains 217 tests: the existing 199 backend/foundation tests (with
updated layout/default-student-login expectations) plus 18 request-level
integration tests. They exercise full sign-in/proficiency/course/comparison/
recommendation/history flow, zero versus unknown, registration and audit,
password fidelity, published content, withdrawal, private deletion, cross-account
access, role removal, CSRF, no-store headers, profile allowlists, and escaping.

Browser verification uses headless Chrome with synthetic content created through
real review/publication services in temporary PostgreSQL. Desktop and mobile
screenshots cover landing/dashboard/results; the browser signs in, submits a
proficiency, runs a comparison, and follows connected navigation. The mobile
layout is checked for horizontal overflow. Temporary servers, browser dependencies,
and databases are removed afterward; the user's application data is untouched.
