# Compass

A Digital Corsairs senior project helping Jackson State University students connect
skills and coursework to career opportunities. Built with Django templates and
PostgreSQL. Docker Compose runs the database; Django runs in a local Python environment.

## Prerequisites

- Git and Python 3.12 or newer.
- Docker with Compose, such as Docker Desktop. Start Docker before continuing.
- Clone this repository. Run all commands from the project root—the folder
  containing `compose.yaml` and `requirements.txt`.

Use the block for your operating system. Windows commands use **PowerShell**,
not Command Prompt or WSL. The explicit Python paths below do not require
virtual-environment activation or PowerShell execution-policy changes.

## First-time setup

### 1. Install dependencies

**macOS / Linux**

```sh
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**Windows — PowerShell**

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Confirm the reported Python version is at least 3.12. If Windows cannot find
`python`, use `py -3 --version` and `py -3 -m venv .venv` instead.
If `.venv` already exists, skip its creation and run only the install command.
Create a separate environment on each computer; recreate it if you move the project.

### 2. Configure the database

Create `.env` only if it does not already exist.

**macOS / Linux**

```sh
test -f .env || cp .env.example .env
```

**Windows — PowerShell**

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Edit `.env` and set a nonempty `POSTGRES_PASSWORD`. Keep existing settings when
reusing a configured database. Each teammate uses their own `.env`; never commit it.

### 3. Start PostgreSQL and apply migrations

Stay in the project root for these and all later commands. The Django commands
below use the virtual environment created in step 1 and the path to `manage.py`.

**macOS / Linux**

```sh
docker compose up -d --wait db
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py check
```

**Windows — PowerShell**

```powershell
docker compose up -d --wait db
.\.venv\Scripts\python.exe src\backend\manage.py migrate
.\.venv\Scripts\python.exe src\backend\manage.py check
```

### 4. Run Compass

**macOS / Linux**

```sh
.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
```

**Windows — PowerShell**

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py runserver 127.0.0.1:8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Choose **Get started** to
register a synthetic student, or **Log in** with an existing account.

## Daily development

Start Docker, run `docker compose up -d --wait db`, then use your operating
system's **Run Compass** command above.

After pulling dependency or schema changes, rerun the dependency install and
`migrate` commands before starting Django.

Stop Django with `Ctrl+C`. Stop PostgreSQL with `docker compose stop db`.
Database data persists; `docker compose down --volumes` deletes it.

## Test accounts and reference data

For personal student accounts and administrator-authorized maintainer accounts,
see [account provisioning](docs/account-provisioning.md). All accounts share the
standard login page; privileged roles require explicit assignment.

Use synthetic information during development. Registration creates a student
account. To create two demo students and a maintainer:

**macOS / Linux**

```sh
.venv/bin/python src/backend/manage.py create_demo_accounts
```

**Windows — PowerShell**

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py create_demo_accounts
```

This optional command prompts for a demo password and refuses to overwrite existing
accounts. It creates no administrator or reference content.

**Skill, course, career/job, and insight lists start empty.** To load the optional
synthetic demonstration catalog, run from the project root:

**macOS / Linux**

```sh
.venv/bin/python src/backend/manage.py seed_compass
```

**Windows ? PowerShell**

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py seed_compass
```

The command creates sample reference content through validated publication services;
it creates no student login or student proficiency by default. Re-running it skips
existing content by kind/title. Use only synthetic data. The optional
`--demo-student EMAIL` argument overwrites that existing student's sample skill
levels/evidence, selects courses, and creates another comparison each run.
See [pilot integration](docs/architecture/pilot-ui-sync.md) and
[sample-data conventions](seeds/README.md).

## Run tests

Keep PostgreSQL running, then use the appropriate command.

**macOS / Linux**

```sh
.venv/bin/python src/backend/manage.py test core accounts skills reference comparisons auditing pilot
```

**Windows — PowerShell**

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py test core accounts skills reference comparisons auditing pilot
```

Tests use a separate PostgreSQL test database.

## Project guides

- [Branch integration checklist](docs/architecture/integration-checklist.md): shared decisions, lead-specific findings, and merge verification.
- [Frontend integration](docs/architecture/frontend-integration.md): routes, supported screens, and remaining work.
- [Development setup](docs/development.md): database settings and troubleshooting.
- [Django command reference](docs/django-commands.md): migrations, tests, accounts, and audit cleanup.
- [Django architecture](docs/architecture/README.md): app responsibilities and service conventions.
- [ERD mapping](docs/architecture/erd-django-mapping.md): account models and database relationships.

The working UI is in `src/backend/core/templates/core/` and its app-owned static
assets. The standalone `frontend/` directory is an older design reference.

Command references: [Python virtual environments](https://docs.python.org/3/library/venv.html)
and [PowerShell Test-Path](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/test-path).
