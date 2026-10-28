# Compass — Digital Corsairs Senior Project

Compass helps Jackson State University students connect coursework and skills to
career opportunities. The team is establishing a Django foundation before
implementing accounts, private profiles, skill comparisons, and recommendations.

## Current status

The `django-structure` branch has a conventional Django project (`config`) and
feature apps (`core` and `accounts`). Django renders a minimal home page through
shared templates. The original six-page HTML/CSS/JavaScript draft remains in
`frontend/` for reference and can be replaced as the design develops.

Authentication, student models, comparisons, and database integration are not
implemented here. The auth/session/admin components are registered, but database
access is disabled and no admin or sign-in route is exposed yet. No account
migrations have been created or applied. Account-model decisions must be settled
before configuring the database and running initial migrations.

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
│   │   ├── urls.py             Included; no account routes yet
│   │   ├── models.py           Placeholder pending user-model agreement
│   │   ├── views.py
│   │   ├── admin.py
│   │   ├── tests.py
│   │   ├── migrations/         Future account schema migrations
│   │   └── templates/accounts/
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

## Run Django locally

From the repository root with Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
```

Reuse `.venv` if it already exists. Open <http://127.0.0.1:8000/> and stop the
server with `Ctrl+C`. Do not run `migrate`, `makemigrations`, or `createsuperuser`
yet. The dummy database backend deliberately prevents accidental creation of the
default account schema while the custom-user model is still being agreed.

Optional settings are documented in `.env.example`. Export them in your shell;
Django does not automatically load `.env` files. Local defaults work without
configuration. Debug defaults to true with a temporary process-local secret;
when debug is disabled, an explicit `DJANGO_SECRET_KEY` is required. This is a
local development foundation, not a completed production deployment setup.

## Run tests

From the repository root:

```sh
.venv/bin/python src/backend/manage.py test core accounts
```

Or activate the environment, change into `src/backend`, and run
`python manage.py test`. Explicit app labels from the repository root avoid
missing tests beneath the non-package `src/` directory.

The current tests cover home-page routing, template inheritance, static asset
discovery, and the absence of unfinished account/admin routes. They prohibit
database access. Authentication and ownership tests will accompany those features.

## View the standalone design draft

```sh
python3 -m http.server 8001 --bind 127.0.0.1 --directory frontend
```

Open <http://127.0.0.1:8001/pages/index.html>. These pages use mock data and are
separate from Django's current minimal home page. Editing them does not update
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
- Coordinate the custom user model, account identifiers, student-profile
  relationship, and migration ownership before initial database migrations.
- Use synthetic student data. Enforce private-record ownership in backend
  operations and test cross-account access when private data is implemented.
- Add runtime packages when they are used. Django is the current runtime;
  PostgreSQL integration dependencies will be added when needed.
- Keep real credentials out of source control and frontend assets. Document
  exported environment settings in `.env.example`.
