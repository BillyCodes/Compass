# Django commands for Compass

Run these commands from the repository root, the folder containing `compose.yaml`.
Use the Python executable in your own `.venv`; activation is not required. Complete
[the first-time setup](../README.md#first-time-setup) and start PostgreSQL before
running commands that read or change database records. Windows examples use
**PowerShell**.

Django connects to the PostgreSQL database selected by your local `.env`. A Git
branch contains models and migration files, but it does not contain another
teammate's local database records or passwords.

## Start and inspect the application

| Task | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| Check Django configuration | `.venv/bin/python src/backend/manage.py check` | `.\.venv\Scripts\python.exe src\backend\manage.py check` |
| Start the local server | `.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000` | `.\.venv\Scripts\python.exe src\backend\manage.py runserver 127.0.0.1:8000` |
| Show available commands | `.venv/bin/python src/backend/manage.py help` | `.\.venv\Scripts\python.exe src\backend\manage.py help` |
| Explain one command | `.venv/bin/python src/backend/manage.py help migrate` | `.\.venv\Scripts\python.exe src\backend\manage.py help migrate` |

Start Docker Desktop or another Docker engine, then start the database with
`docker compose up -d --wait db`. Stop the server with `Ctrl+C`; stop the database
with `docker compose stop db`. The database volume persists after a stop.

## Migrations and schema changes

| Task | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| See which migrations have run | `.venv/bin/python src/backend/manage.py showmigrations` | `.\.venv\Scripts\python.exe src\backend\manage.py showmigrations` |
| Preview pending migration operations | `.venv/bin/python src/backend/manage.py migrate --plan` | `.\.venv\Scripts\python.exe src\backend\manage.py migrate --plan` |
| Check that model edits have matching migration files | `.venv/bin/python src/backend/manage.py makemigrations --check --dry-run` | `.\.venv\Scripts\python.exe src\backend\manage.py makemigrations --check --dry-run` |
| Create a migration after editing an app's models | `.venv/bin/python src/backend/manage.py makemigrations reference` | `.\.venv\Scripts\python.exe src\backend\manage.py makemigrations reference` |
| Apply committed migrations locally | `.venv/bin/python src/backend/manage.py migrate` | `.\.venv\Scripts\python.exe src\backend\manage.py migrate` |

Replace `reference` in the creation example with the app you changed. Review and
commit the generated migration alongside the model change. When testing a
teammate's branch, run `makemigrations --check --dry-run` to detect a missing
migration; do not create one just to make their branch pass. Inspect `migrate
--plan` before applying migrations to a database containing useful records.

## Tests

| Task | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| Run Compass's app tests | `.venv/bin/python src/backend/manage.py test core accounts skills reference comparisons auditing` | `.\.venv\Scripts\python.exe src\backend\manage.py test core accounts skills reference comparisons auditing` |
| Run one app's tests | `.venv/bin/python src/backend/manage.py test reference` | `.\.venv\Scripts\python.exe src\backend\manage.py test reference` |
| Run one test module | `.venv/bin/python src/backend/manage.py test reference.tests.test_publication` | `.\.venv\Scripts\python.exe src\backend\manage.py test reference.tests.test_publication` |

Django creates a separate test database and removes it when the run finishes.
Tests require the local PostgreSQL server and permission to create a database.
The local Compose database user has that permission. For a teammate's schema
changes, also try the affected workflow manually against a separate local
database; see [development setup](development.md#postgresql-with-compose).

## Local accounts

| Task | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| Create the initial synthetic accounts | `.venv/bin/python src/backend/manage.py create_demo_accounts` | `.\.venv\Scripts\python.exe src\backend\manage.py create_demo_accounts` |
| Change the local demo maintainer's password | `.venv/bin/python src/backend/manage.py changepassword maintainer@example.test` | `.\.venv\Scripts\python.exe src\backend\manage.py changepassword maintainer@example.test` |

`create_demo_accounts` prompts for a password and creates two students plus one
maintainer. It refuses to replace existing accounts. Passwords are stored as
hashes, so the original password cannot be displayed or recovered. The
`changepassword` command prompts twice and updates only the account in the
PostgreSQL database currently selected by your `.env`. It does not affect a
teammate's local database.

The maintainer role is separate from Django's `is_staff` and `is_superuser`
flags. This project does not expose a Django admin URL, so `createsuperuser` is
not part of the normal Compass setup.

## Audit retention

| Task | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| Preview audit events older than one year | `.venv/bin/python src/backend/manage.py purge_audit_events` | `.\.venv\Scripts\python.exe src\backend\manage.py purge_audit_events` |
| Purge those expired events | `.venv/bin/python src/backend/manage.py purge_audit_events --execute` | `.\.venv\Scripts\python.exe src\backend\manage.py purge_audit_events --execute` |

The preview does not delete records. `--execute` permanently deletes only audit
events beyond the one-calendar-year retention period. See the
[audit design guide](architecture/audit-batch.md) for the retention rule.

## Before using commands on a teammate's branch

Check `git status` so you know which work is already in your checkout. Review
the teammate's model and migration files together. Use a separate database when
trying migrations or seed data, then run the migration checks and relevant tests
above. Hand-entered PostgreSQL records are local to the computer where they were
created; ask for a repeatable seed command or sanitized export when the test
needs those records.
