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
that Django credentials or application tables work. You can inspect the empty
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

## Django integration boundary

Django intentionally still uses the dummy database backend. Starting this container
does not configure Django, apply migrations, create account tables, or seed data.
The existing foundation page and tests continue to work without Docker.

After the custom-user and profile decisions are settled:

1. Add a pinned compatible Psycopg 3 driver to Python requirements.
2. Configure `django.db.backends.postgresql` using the agreed environment settings.
   Host-run Django connects to `127.0.0.1` and the chosen host port. If Django is
   later containerized in the same Compose project, it connects to `db:5432`.
3. Set `AUTH_USER_MODEL` and create the agreed initial app migrations. Review and
   commit models and migrations together, then apply those same migrations in each
   development database.
4. Test account creation, sessions, ownership, and database constraints against
   PostgreSQL. No migration or seed command will run automatically at startup.

Compose reads root `.env` values automatically. That does not export them to the
host Django process. Django's environment-loading approach will be implemented
alongside its database settings rather than silently assuming they are shared.

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
