# Django architecture

Foundation established on `django-structure`, October 28, 2026. This branch contains
project wiring and a minimal home page; authentication and database models remain
future work.

## Responsibilities and locations

| Location | Responsibility |
| --- | --- |
| `src/backend/manage.py` | Django management commands |
| `src/backend/config/` | Project settings, root URL composition, WSGI/ASGI entry points |
| `src/backend/core/` | Public pages and shared site layout assets; not a home for unrelated business logic |
| `src/backend/accounts/` | Future account model, authentication, and account permissions |
| `src/backend/templates/` | Shared base template and header/footer includes |
| `<app>/templates/<app>/` | Namespaced templates owned by a feature app |
| `<app>/static/<app>/` | Namespaced CSS, JS, and images owned by that app |
| `<app>/migrations/` | Versioned schema changes owned by that app |
| `<app>/tests/` or `<app>/tests.py` | Tests for that app; use one form per app |
| `tests/` at repository root | Reserved for future workflows spanning multiple apps |
| `frontend/` | Preserved standalone design draft; CSS/JS also discoverable under `/static/draft/` |
| `staticfiles/` | Ignored generated `collectstatic` output, not source files |

The former repository-root migrations placeholder has been removed. Future Django
migrations belong to each owning app. No database schema migrations were created
or applied.

## Request flow

`config/urls.py` includes an app's URL configuration. The app maps a named route
to a view. The view handles the request and renders a template or returns data.
Templates extend the shared `base.html`; future models provide persistence when
the data design is approved.

The initial route is `core:home` at `/`. `accounts/urls.py` is included but has no
routes until account implementation starts. `/admin/` is deliberately not exposed
until account/database configuration is ready. Earlier sign-in work on another
branch has not been copied into this foundation.

## Configuration boundary

- The ordinary Django auth, sessions, messages, and admin components remain
  registered so the project is ready for their future integration.
- Database configuration uses the dummy backend. This prevents accidentally
  migrating Django's default user schema while the custom-user decision is open.
  Account/admin operations and database queries are not supported at this stage.
- Confirm the user model, account identifier type, student relationship, and
  migration responsibilities before configuring the database and initial
  migrations. Username login is the selected direction.
- Environment values are read from exported variables, not automatically from
  `.env` files. Debug defaults to true for local development. A process-local random
  secret is used only when debug is enabled and no explicit key is exported.
- With debug disabled, an explicit `DJANGO_SECRET_KEY` is required. Production
  deployment still needs database, HTTPS, static hosting, and session configuration.
- `requirements.txt` contains Django only. Unused FastAPI/SQLAlchemy/JWT packages
  were removed from the declared runtime; installed environment packages were not
  uninstalled. Add PostgreSQL dependencies when that integration is implemented.

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
5. Commit model changes with app migrations after the account-design agreement.
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
