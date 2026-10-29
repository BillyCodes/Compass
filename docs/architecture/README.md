# Django architecture

Foundation established on `django-structure`, October 28, 2026. This branch contains
project wiring, a placeholder home page, and the first account/authentication
milestone. See [ERD-to-Django mapping](erd-django-mapping.md) for the implemented
Account, Student, Role, and AccountRole models.

The agreed PostgreSQL Compose setup, Django-template frontend direction, and
Mockaroo data workflow are documented in [Team development setup](../development.md).
Django now connects to the Compose database using the root `.env` settings.

## Responsibilities and locations

| Location | Responsibility |
| --- | --- |
| `src/backend/manage.py` | Django management commands |
| `src/backend/config/` | Project settings, root URL composition, WSGI/ASGI entry points |
| `src/backend/core/` | Public pages and shared site layout assets; not a home for unrelated business logic |
| `src/backend/accounts/` | Email account, student profile, role models, authentication, and access checks |
| `src/backend/templates/` | Shared base template and header/footer includes |
| `<app>/templates/<app>/` | Namespaced templates owned by a feature app |
| `<app>/static/<app>/` | Namespaced CSS, JS, and images owned by that app |
| `<app>/migrations/` | Versioned schema changes owned by that app |
| `<app>/tests/` or `<app>/tests.py` | Tests for that app; use one form per app |
| `tests/` at repository root | Reserved for future workflows spanning multiple apps |
| `frontend/` | Preserved standalone design draft; CSS/JS also discoverable under `/static/draft/` |
| `staticfiles/` | Ignored generated `collectstatic` output, not source files |

The former repository-root migrations placeholder has been removed. Future Django
migrations belong to each owning app. The initial account schema and role-seed
migrations now live in `accounts/migrations/`.

## Request flow

`config/urls.py` includes an app's URL configuration. The app maps a named route
to a view. The view handles the request and renders a template or returns data.
Templates extend the shared `base.html`; account models now provide persistence
for the first ERD section.

The public home route is `core:home`. `accounts/urls.py` provides email login,
POST-only logout, and private profile reads. `/admin/` is still not exposed;
privileged model-management screens are deferred.

## Configuration and identity

- `AUTH_USER_MODEL` points to the UUID-based `accounts.Account`; email login
  supersedes the previous username choice. The initial migration defines this
  custom model before its dependent application tables.
- Django connects to PostgreSQL through Psycopg 3. Both Django and Compose read
  root `.env`; exported shell values take precedence. Do not commit credentials.
- Django authentication/session infrastructure is separate from Compass business
  roles. `AccountRole` is authoritative for business role checks; Groups and admin
  flags are not used as a duplicate business-role system.
- Profile reads filter on the signed-in account. A role or UUID alone never grants
  another student's private profile access.
- Debug defaults to true with a temporary process-local secret if none is exported.
  Set a stable local key to preserve sessions across restarts. Production needs
  separate configuration, a shared throttle cache, and HTTPS.
- Runtime requirements now include Django, Psycopg 3, and python-dotenv.

## Adding functionality

1. Add a feature app when a coherent responsibility needs implementation. For
   example, comparisons should own comparison rules rather than placing them in
   `core` or `config`. There is no need to pre-create every planned app.
2. Give the app its own `urls.py` with `app_name`, then include it from the root
   URL configuration. Use namespaced route names in templates.
3. Keep views focused on HTTP handling. Extract substantial calculation or
   recommendation logic into the owning app's `services.py` or `services/` package
   when needed; that convention is optional rather than required by Django.
4. Put shared presentation in the project templates and feature presentation in
   the app. The programming lead can replace templates and styles without changing
   the app's models or service logic.
5. Review and commit model changes with app migrations.
   Use synthetic data and include tests of behavior and ownership boundaries.

## Validation

From the repository root:

```sh
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py test core accounts
```

Alternatively, activate the environment, change into `src/backend`, and run
`python manage.py test` for default discovery from the Django project directory.
When invoking tests from the repository root, explicitly list the apps because
`src/` is not configured as a test-discovery package.

## References

- [Django project and app structure](https://docs.djangoproject.com/en/6.1/intro/tutorial01/)
- [App-owned templates and static files](https://docs.djangoproject.com/en/6.1/intro/reusable-apps/)
- [Choose a custom user model before initial migrations](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#using-a-custom-user-model-when-starting-a-project)
