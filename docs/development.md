# Team development stack

Agreed direction, October 28, 2026:

- Django is the backend, with its ORM and migrations defining the shared schema.
- The programming lead's HTML/CSS/JavaScript frontend will become Django templates.
- PostgreSQL runs locally through the shared Docker Compose configuration.
- Mockaroo provides synthetic sample data that can be imported repeatedly.

## PostgreSQL with Compose

The Compose file starts only PostgreSQL. Django continues running in the host's
virtual environment. Every developer uses the same configuration with their own
local container and named data volume; this is not one remotely shared database.

Prerequisites: Docker with Compose v2 and a running Docker engine (for example,
Docker Desktop). The team baseline is the official `postgres:17-bookworm` image.
This fixes the major version and OS family while allowing minor/security updates;
it does not pin an immutable image digest. Coordinate version changes in Git.

From the repository root:

1. If `.env` does not exist, copy `.env.example` to `.env`. Otherwise, add only the
   missing PostgreSQL settings to your existing file. Do not overwrite existing
   credentials or settings.
2. Set a nonempty local-only `POSTGRES_PASSWORD`. The supplied example deliberately
   leaves it empty, and Compose refuses to start without a value.
3. Check configuration and start the database:

   ```sh
   docker compose config --quiet
   docker compose up -d --wait db
   docker compose ps
   ```

The database is available to host applications at `127.0.0.1:5432`, with database
and user defaulting to `compass`. If that port is occupied, change `POSTGRES_PORT`
in `.env`, for example to `5433`. The container itself still uses port 5432.

The health check uses `pg_isready` to check server readiness; it does not prove
that Django credentials or application tables work. You can inspect the
database without making schema changes:

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version();"'
```

Stop with `docker compose stop db`, or remove the container/network with
`docker compose down`. The named data volume persists through both. Do not use
`down --volumes` unless you intend to erase the local database. Changing passwords,
user names, or database names in `.env` does not reinitialize an existing volume;
coordinate actual database changes separately. The image's environment settings
initialize a new empty data directory only.

The published port is restricted to loopback. The image's initial user has database
superuser privileges; these credentials are for local synthetic-data development,
not production application access.

## Django and authentication

Django now connects to PostgreSQL using Psycopg 3 and the root `.env` settings.
`python-dotenv` reads that file without overriding exported shell variables.
Host-run Django uses `POSTGRES_HOST=127.0.0.1` (the default) and `POSTGRES_PORT`.
If Django is later containerized, its host would be `db` and port `5432` instead.

The custom email-login account model is configured before the initial migration.
See [ERD-to-Django mapping](architecture/erd-django-mapping.md) for the four models,
Django field mappings, constraints, role boundaries, and deletion behavior.

From the repository root, with Docker running and `.env` configured:

```sh
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --wait db
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py create_demo_accounts
.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
```

The demo command prompts for a shared strong password for three synthetic
accounts, without echoing or storing it in repository files:

- `student.a@example.test` with a student profile and role.
- `student.b@example.test` with a different student profile and role.
- `maintainer@example.test` with a maintainer role and no student profile.

It refuses to modify existing demo accounts on repeat runs. No administrator,
staff, or superuser account is created. Use a synthetic password, not a personal
password. Public registration and privileged role-management screens are deferred.

Open <http://127.0.0.1:8000/accounts/login/>. A valid email/password opens the
account's profile; logout uses POST and ends access. Login is case-insensitive for
email addresses. The underlying form field is named `username` for compatibility
with Django's AuthenticationForm; no username account column exists.

Set a stable local `DJANGO_SECRET_KEY` in your ignored `.env` if you want sessions
to survive server restarts; otherwise debug mode uses a temporary process key.
Production keys must be separate. Compose does not run migrations or seeds on
startup. Only Django migrations define the application schema.

Run the PostgreSQL-backed suite with:

```sh
.venv/bin/python src/backend/manage.py test core accounts
```

Django creates and destroys an isolated `test_compass` database (or `test_` plus
your configured database name). These tests verify database uniqueness, email
login, ownership, disabled accounts, role checks, CSRF, logout, safe redirects,
and a local failed-login throttle. Foundation tests still forbid database queries,
but running the full suite now requires PostgreSQL and database-create privileges.
The container's local development user has those privileges.

The throttle is per-process and uses the direct peer IP. A deployment with proxies
or multiple workers needs explicit proxy handling and a shared cache. This setup
is for local testing; email verification, password reset, and production access
configuration remain future work.

## Frontend integration

Keep the programming lead's design as the source for the eventual UI. Put common
page structure in `src/backend/templates/base.html` and includes; put feature
templates and static assets in their owning apps. Use named Django URLs, static
tags, and CSRF tokens when connecting forms. The current placeholder layout is
replaceable. No separate API frontend, React migration, or Django REST Framework
dependency is required by this decision.

## Schema and sample-data workflow

```text
Reviewed ERD -> Django models -> committed migrations -> PostgreSQL schema
Saved Mockaroo schema -> saved CSV/JSON export -> Django importer -> sample rows
```

Django migrations own schema changes. Mockaroo exports supply data, not a second
schema definition or competing CREATE TABLE scripts. See [sample-data conventions](../seeds/README.md).

## References

- [Compose environment interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [Official PostgreSQL image and initialization behavior](https://hub.docker.com/_/postgres)
- [Django PostgreSQL requirements](https://docs.djangoproject.com/en/6.1/ref/databases/#postgresql-notes)
