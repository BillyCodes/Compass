# Docker + test-launch integration

## Source snapshots

- Foundation: `Docker-PostgreSQL-Setup` at `734b4f0aa44172599a825e7d3051a8028849b8bd`.
- Feature source: `compass-test-launch` at `bcaea9a1ed2de13caf891b379cba4233b48985e4`.
- Integration: `integration/docker-test-launch`, based on the foundation.

Feature files were ported into `src/backend/core` and adapted; the launch project's
root `manage.py` and `compass_site` settings were not introduced. Neither source
branch is changed by this PR.

## Step 1 — reconcile the account designs

| Area | Docker foundation | Test launch | Integration |
| --- | --- | --- | --- |
| Identity | `accounts.Account`, UUID, `login_email`, `password_hash` column | `core.Account`, `email`, role/status fields | Keep foundation model and case-insensitive email uniqueness |
| Profile | `accounts.Student`, UUID, `display_name`, graduation year | `core.Student`, `name` | Keep foundation profile; API `name` maps to `display_name` |
| Roles | Role + AccountRole; guarded assignment service | Single account role | Keep separate role assignments; registration creates only student role |
| Migrations | accounts 0001 + role seed 0002 | core initial includes its own identity tables | Preserve accounts files unchanged; new core 0001 depends on accounts 0002 |
| Routes | `core:home`, `/accounts/` login/logout/profile/UUID detail | Student pages and `/api/` | Retain old routes, add launch routes and home alias |
| Forms/views | Django AuthenticationForm, owner-filtered profiles | Registration, login, editing and student workflow | Adapt account field names, use transactional student service, preserve API payloads |
| Tests | Account constraints, ownership, roles, auth; static home | Journey, comparisons, resume, negative/API tests | Keep account tests; adapt launch schema references and home expectations; add cross-branch tests |

`Account` and `Student` imported by `core.models` are the foundation classes,
not additional models. Every private feature foreign key targets `accounts.Student`.
The `first_name` property added to Student is presentation-only and changes no schema.

## Step 2 — keep one runtime

Compose still runs PostgreSQL 17; Django runs in the host virtual environment.
Continue using the root `.env` and `POSTGRES_*`/`DJANGO_*` variables. There is no
SQLite fallback or second settings module. WhiteNoise was configured in the
foundation but missing from requirements; it is now included. Resume processing
adds pypdf and python-docx. Launch upload bounds and ten-character minimum
registration passwords are configured in the existing settings.

The old `/accounts/login/` accepts `username` (an email address); the launch
`/login/` and `/api/login` accept `email`. All use the same user model and sessions.
The old sign-in default remains `/accounts/profile/`; launch sign-in goes to
`/dashboard/`. Existing no-profile maintainers retain their account profile page
and cannot access the student API. Launch redirect targets use Django's host/scheme
validation. CSRF, POST-only logout and ownership checks remain enabled.

## Step 3 — apply to a Docker-foundation database

Back up any database whose contents matter before applying migrations. From the
repository root, with the existing root `.env` configured:

```sh
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --wait db
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py collectstatic --noinput
.venv/bin/python src/backend/manage.py runserver
```

Existing account/student UUIDs, password hashes, profile fields and role assignments
remain in place. The new migration adds only feature tables and constraints.
Do not replace the accounts migrations, fake migration history, or reset the
PostgreSQL volume. This migration supports a Docker-foundation database; it is
not a data-import procedure for an already-populated `core.Account` launch database.
Such a database needs a separately designed export/import mapping.

For a disposable local pilot database, optionally run:

```sh
.venv/bin/python src/backend/manage.py seed_compass
```

This imports the launch's synthetic catalogs, fictional content and documented
local demo accounts (`student.a@compass.test` / `CompassDemo-A1`,
`student.b@compass.test` / `CompassDemo-B2`, plus a disabled account).
Existing accounts are skipped. `--reset` deletes and recreates these demo accounts
and their related records; do not use it against data you want to retain.
The foundation's interactive `create_demo_accounts` command also remains available.

## Step 4 — review and validate

```sh
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
.venv/bin/python src/backend/manage.py test accounts core --noinput
```

Validated on November 3, 2026: **68 tests passed** on Python 3.14 / Django 6.1.2 /
PostgreSQL 17; system checks and migration drift checks passed; 136 static assets
collected; synthetic seeding succeeded on two consecutive runs.

Validation uses an isolated PostgreSQL 17 container, not the user's existing
Compose database. An upgrade rehearsal first installs the accounts migrations,
creates an account/profile/role assignment, then applies core migrations and checks
that IDs, password hash, graduation year and role assignment survive. A new skill
is then linked to that same student UUID.

Reviewer walkthrough:

1. Sign in with an existing foundation account through either login page.
2. Open `/dashboard/`, add a skill and course, upload a small sample resume.
3. Compare against a seeded career, inspect the result and save progress.
4. Edit `/profile/`; confirm `/accounts/profile/` sees the same profile.
5. Sign out and verify protected pages require login; use the second demo account
   to confirm the first student's saved results remain private.

The launch is still a local pilot: login throttles use an in-process cache and
synthetic seeds include public demo passwords. Deployment hardening and importing
an existing launch database are outside this integration.
