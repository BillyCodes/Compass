# Compass handoff: continue on MacBook

Updated November 12, 2026. This is a project-context summary, not a verbatim chat
export. Inspect the current branch and checklist before changing code; this file
records the state at handoff and may become outdated.

## Where we are

- Branch at handoff: `real-world-data`.
- Latest implementation commit inspected: `a3b7643` (account provisioning).
  Preceding commits include `42d21f1` (provenance) and `73af13b` (curation docs/data).
- Compass is a Django-template/PostgreSQL senior project. Docker Compose runs
  PostgreSQL; Django runs in a machine-local Python virtual environment.
- The full suite last passed **325 tests**, including bootstrap concurrency,
  account provisioning, provenance upgrades and publication/history guards.
- Phase 1 (provenance/original notes) and Phase 4 (non-demo account provisioning)
  of the [curated-content checklist](architecture/curated-content-checklist.md)
  are implemented. Provider-specific dashboard work, imports and broader
  attribution/presentation work remain.

## Decisions to preserve

- Content maintainers and business administrators publish directly; do not
  reinstate independent second-person approval. Retain sources/provenance checks,
  revision checks, immutable published history, successor drafts and retirement.
- Student proficiency is 0–5; zero differs from unreported. Courses/resources
  never award proficiency automatically. Comparisons use `weighted_skill_match_v1`.
- Career matching requirements, weights, mandatory flags and learning coverage
  are Compass-authored interpretations unless explicitly supported by a source.
- Curated catalog: five computing careers using O*NET/BLS; seven initial linked
  MIT OCW learning resources; clearly attributed original personal reflections.
  Real employer job feeds/scraping are outside this batch. Keep synthetic job
  postings and seed accounts for development; do not load them into the curated DB.
- Public registration creates a student only. Maintainer access comes from an
  explicitly assigned business role, not a special email or Django staff flag.
- Use separate personal student, maintainer and administrator accounts initially.
  Credentials are chosen locally; none belong in Git or this handoff.
- Public hosting remains deferred. This is a local senior-project presentation,
  not an active service collecting other students' private records.

## Implemented foundations

### Content and sources

- Migrations `reference/0009_content_provenance` and
  `reference/0010_provenance_publication_guards` add structured source metadata,
  per-edition usage/changes/credits, origin classification and publication guards.
- Existing editions migrate to `legacy`, without invented licenses or modified
  historical bodies. Legacy successor drafts must be classified before publication.
- Origins: external, original, synthetic and legacy. Original reflections must
  be insights with an author and originality/borrowed-material confirmation.
  They can publish without fabricated external citations. Any attached borrowed
  material still receives provenance checks.
- Source metadata includes provider/publisher/author, canonical URL, license,
  attribution, edition, external ID, file checksum and raw JSON metadata.
- Generic maintainer forms expose these fields. Detail pages for Field Notes,
  learning resources and reference comparison results display source credits.
  Provider-specific starting actions and full attribution coverage remain pending.
- Read the checklist for link-only versus copied/adapted content. Metadata
  validation does not itself establish that a claimed license is accurate.

### Accounts

- `bootstrap_administrator EMAIL`: creates only the first new business
  administrator in the selected database. Refuses existing emails or any prior
  administrator assignment, including disabled accounts. Concurrent bootstrap
  attempts are serialized. Passwords are prompted privately and validated.
- `manage_maintainer create|grant|revoke EMAIL --administrator ADMIN_EMAIL`:
  authenticates an active business administrator; uses audited role services.
  Creation refuses existing accounts; granting refuses student accounts/profiles.
- No automatic startup provisioning, password arguments, or Django admin grants.
- Shared login routes students to `/dashboard/` and editors to `/maintainer/`.
  A safe explicit `next` destination takes precedence. Role revocation and
  account deactivation affect subsequent requests, including existing sessions.
- See [account provisioning](account-provisioning.md) for full instructions.

### Earlier fixes already implemented

- Atomic private-posting creation/comparison; failure rolls back new posting,
  requirements and first result. Existing history survives failed reruns.
- Dashboard job ranking happens in SQL; only winners load for Python scoring.
- Course selection, selected cards and learning links share availability rules.
  Existing unavailable selections remain readable as history.
- Pagination empty messages refer to the current page where appropriate.
- Radar categories average up to three reported skills without zero padding.
  Snapshot scoring versions prevent false progress across formula changes.

## Source data and research

- Raw files: `data/reference/onet/31.0/occupation_data.csv` and
  `data/reference/onet/31.0/software_skills.csv`; preserve these original files.
- [Source README](../data/reference/onet/31.0/README.md) records downloads/license.
- [Curated catalog sources](architecture/curated-catalog-sources.md) maps five
  occupations to BLS profiles and seven MIT resources with proposed associations.
- Initial occupation codes: Software Developers `15-1252.00`, Information Security
  Analysts `15-1212.00`, Data Scientists `15-2051.00`, Computer Systems Analysts
  `15-1211.00`, Database Architects `15-1243.00`.
- Respect O*NET CC BY 4.0 attribution/adaptation requirements and exceptions;
  cite BLS and preserve wage years/geographies/projection periods; follow MIT's
  applicable CC BY-NC-SA terms and individual-resource exceptions when copying or
  adapting. Initially link to MIT resources. Keep personal reflections identifiable.
- No curated importer or actual real-content publication has been completed.

## Database state and the Windows terminal issue

- Windows has separate `compass` (synthetic development) and `compass_curated`
  databases inside the same PostgreSQL container.
- `compass_curated` was created and fully migrated in this conversation. It had
  three role records and zero accounts/content when inspected. Subsequent manual
  account creation is unverified; do not assume it remained empty.
- Seeing seeded content came from running against the original DB. The user
  subsequently verified `compass_curated` as the selected Django database.
- Windows Command Prompt uses `set POSTGRES_DB=compass_curated`; PowerShell uses
  `$env:POSTGRES_DB = "compass_curated"`. Mac zsh uses `export` as below.
- Shell environment overrides `.env`. Set the variable before starting Django
  or provisioning accounts, in the same terminal. Restart an already-running
  server to change its database. The override is not automatically persistent.
- Git transfers code/docs/CSVs, not `.env`, virtual environments, passwords,
  accounts or Docker database volumes. A database export/restore would be a
  separate action; none has been performed.

## MacBook setup

1. Commit/push this handoff on Windows, then pull branch `real-world-data` on the
   Mac. Check `git status` and preserve any existing work. Follow the root README
   for Python prerequisites and database configuration.
2. Create a fresh Mac virtual environment, install dependencies and configure a
   local ignored `.env`. Do not overwrite an existing `.env` unnecessarily:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   test -f .env || cp .env.example .env
   ```

   Set a nonempty `POSTGRES_PASSWORD` in `.env` before starting PostgreSQL.

3. Start Docker Desktop. From the project root, start PostgreSQL before exporting
   the Django database override:

   ```sh
   docker compose up -d --wait db
   docker compose exec db createdb -U compass -O compass compass_curated
   export POSTGRES_DB=compass_curated
   .venv/bin/python src/backend/manage.py migrate
   .venv/bin/python src/backend/manage.py check
   .venv/bin/python src/backend/manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
   ```

   The creation command is one-time and assumes default database user `compass`.
   If the database already exists, preserve it and proceed with migrations.
   Verify that the printed database name is `compass_curated`.

4. In that same terminal, provision new personal accounts when needed. Replace
   placeholders with email addresses/aliases controlled by the user:

   ```sh
   .venv/bin/python src/backend/manage.py bootstrap_administrator admin@your-domain.edu
   .venv/bin/python src/backend/manage.py manage_maintainer create editor@your-domain.edu --administrator admin@your-domain.edu
   .venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
   ```

   Use public registration for the personal student account. Do not run
   `seed_compass` or `create_demo_accounts` in this curated database. Export the
   database variable again in each new terminal. User types passwords privately.

5. Validate the installation against a separate test database:

   ```sh
   .venv/bin/python src/backend/manage.py makemigrations --check --dry-run
   .venv/bin/python src/backend/manage.py test core accounts skills reference comparisons auditing pilot --noinput
   ```

## Next work

First verify the Mac setup, selected database and account roles. Then continue
Phases 2–3 of the curated-content checklist: provider-aware dashboard actions,
source picker/presets, previews, source-specific review and attribution. Implement
a small dry-run/repeatable O*NET-to-draft importer and the career-first presentation
after those foundations. Preserve the current schema guards and completed work.

Suggested opening prompt in a new assistant conversation:

> Read docs/macbook-handoff.md, docs/architecture/curated-content-checklist.md,
> docs/architecture/curated-catalog-sources.md and docs/account-provisioning.md.
> Check the current Git state and Mac environment before changing anything.
> Phases 1 and 4 are implemented. Help verify compass_curated and personal account
> setup, then continue the provider-aware maintainer dashboard work in Phases 2–3.
