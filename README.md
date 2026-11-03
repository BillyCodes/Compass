# Compass — Digital Corsairs Senior Project

Compass helps Jackson State University students connect coursework and skills to
career opportunities. The team is building
Django account authentication first, followed by skill comparisons and recommendations.

## Current status

The codebase has a conventional Django project (`config`) and
feature apps (`core`, `accounts`, `skills`, `reference`, `comparisons`, and `auditing`).
This branch has imported the new Django templates, stylesheet, and template helpers
for integration. Their routes, forms, and view context are not connected yet; the
imported homepage currently fails to reverse the pilot URL names. Existing
account routes still use the legacy layout, which depends on `frontend/css/style.css`.
The original standalone draft remains in `frontend/` for reference. See the
[frontend cleanup review](docs/architecture/frontend-cleanup-review.md) for active
dependencies, safe cleanup, and the integration checklist.

The first ERD section is now implemented: Account, Student, Role, and AccountRole.
Email/password sign-in uses Django sessions and the local PostgreSQL container.
Private student-profile reads enforce ownership. The student and maintainer demo
accounts are created through an interactive command; public registration, profile
editing and admin screens remain future work. The next schema batch now adds
skills, private student proficiency, and content item/version foundations.
The second reference batch adds companies, sources, source links, typed details,
career/job requirements, and course/resource skill mappings. Reference review/publication services and private course selections are now
implemented. Private comparisons, saved proficiency snapshots, skill outcomes, and
ranked learning recommendations are now available through backend services.
Audit events now record supported role/account and reference-content actions
transactionally, with administrator-only reads and one-year retention. All 21
planned ERD tables are implemented; new frontend management screens remain future work.

See [ERD-to-Django mapping](docs/architecture/erd-django-mapping.md) for how the
diagram's fields and relationships map to Django and PostgreSQL.

See [Skills and reference-content foundation](docs/architecture/skills-reference-foundation.md)
for the new tables, 0–5 proficiency scale, typed foreign key, and draft services.
See [Reference data batch](docs/architecture/reference-data-batch.md) for the six
additional tables and related draft-edit services. No new skill-entry or
content-management screens are included yet. See
[Review/publication batch](docs/architecture/review-publication-batch.md) for the
new course selections, independent approvals, and publication/history guards.
See [Comparison batch](docs/architecture/comparison-batch.md) for the agreed scoring,
private history, and recommendation rules. See [Audit batch](docs/architecture/audit-batch.md)
for event coverage, access, one-year retention, and the maintenance command.

## Project structure

```text
Compass/
├── src/backend/
│   ├── manage.py
│   ├── config/                 Settings, root URLs, WSGI and ASGI
│   ├── core/                   Public pages and site layout assets
│   │   ├── apps.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── templates/core/     Feature-owned page templates
│   │   ├── static/core/        Feature-owned static assets
│   │   └── tests/              Database-free foundation tests
│   ├── accounts/               Account/authentication implementation area
│   │   ├── apps.py
│   │   ├── urls.py             Login, POST logout, private student profiles
│   │   ├── models.py           Account, Student, Role, AccountRole
│   │   ├── views.py
│   │   ├── forms.py            Email authentication form
│   │   ├── services.py         Atomic student setup and guarded role assignment
│   │   ├── managers.py         Email normalization and password hashing
│   │   ├── management/         Interactive synthetic-account setup
│   │   ├── permissions.py      Business role checks
│   │   ├── admin.py
│   │   ├── tests.py
│   │   ├── migrations/         Initial schema and fixed role vocabulary
│   │   └── templates/accounts/
│   ├── skills/                 Skill catalog, student proficiency, services/tests
│   ├── reference/              Versioned reference data, draft services/tests
│   ├── comparisons/            Private scoring, snapshots, recommendations
│   ├── auditing/               Minimal event history and retention maintenance
│   └── templates/              Shared base.html and includes/
├── frontend/                   Preserved standalone design draft
├── tests/                      Reserved for future cross-app workflows
├── docs/                       Architecture, API, and security documentation
├── seeds/                      Reserved for synthetic development data
├── scripts/
├── .env.example
└── requirements.txt
```

See [Django architecture](docs/architecture/README.md) for app responsibilities,
request flow, and conventions for extending the project.

## Agreed development stack

The backend uses Django, with models and migrations defining the shared schema.
The programming lead's HTML/CSS/JavaScript design will be integrated as Django
templates. PostgreSQL has a shared local [Docker Compose configuration](compose.yaml),
and Mockaroo will supply repeatable synthetic sample data. See
[Team development setup](docs/development.md) for database startup instructions
and [sample-data conventions](seeds/README.md) for the import workflow.

Django models and committed migrations define the application schema. Mockaroo
will supply domain datasets; the initial three role names are installed by a data
migration. No privileged account is automatically created.

## Run Django locally

From the repository root with Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --wait db
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py create_demo_accounts
.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
```

Reuse `.venv` if it already exists. Before starting Compose, copy `.env.example`
to `.env` only if that file does not exist, and set a local `POSTGRES_PASSWORD`.
Preserve existing values if `.env` already exists. Django and Compose both read
root `.env`; exported variables take precedence. Full instructions are in
[Team development setup](docs/development.md).

Open <http://127.0.0.1:8000/accounts/login/> and sign in with a synthetic account
created by `create_demo_accounts`, which prompts for a password. Stop the server
with `Ctrl+C`. Migrations run only when explicitly requested; they do not run at
container startup. This is a local development setup.

## Run tests

From the repository root:

```sh
.venv/bin/python src/backend/manage.py test core accounts skills reference comparisons auditing
```

Or activate the environment, change into `src/backend`, and run
`python manage.py test`. Explicit app labels from the repository root avoid
missing tests beneath the non-package `src/` directory.

The 199-test suite covers accounts/authentication, student skills, content
versioning, comparisons, recommendation snapshots, audit history/retention, typed foreign keys, ownership, and role controls on an isolated
PostgreSQL test database. The foundation tests
also check routing, shared templates, and static asset discovery. Keep Docker's
database running when testing.

## View the standalone design draft

```sh
python3 -m http.server 8001 --bind 127.0.0.1 --directory frontend
```

Open <http://127.0.0.1:8001/pages/index.html>. These pages use mock data and are
separate from the imported Django templates. Editing them does not update
Django templates. Django can also discover their CSS/JS under `/static/draft/`.

## Team development conventions

- Organize code into feature apps. Keep global configuration in `config`; do not
  put all business logic into `core`.
- Keep feature routes, views, models, tests, templates, and static assets with the
  owning app. Use namespaced URLs and namespaced app template/static paths.
- Use the shared base template for common page structure. Replace templates/styles
  as the frontend evolves while preserving route names and form contracts.
- Keep migrations inside each owning app, and commit them with model changes.
  The former repository-root migrations placeholder has been removed.
- The custom email-login user and related UUID entities are implemented. Review
  future model changes with Richshard and commit the corresponding app migrations.
- Use synthetic student data. Enforce private-record ownership in backend
  operations and test cross-account access when private data is implemented.
- Runtime requirements include Django, Psycopg 3, and python-dotenv. Add further
  dependencies when their features are implemented.
- Keep real credentials out of source control and frontend assets. Document
  exported environment settings in `.env.example`.
