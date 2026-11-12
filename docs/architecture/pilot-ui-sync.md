# Integrated pilot UI and maintainer workflows

The student UI/features from `5c3752e` are integrated with maintainer work through
`1740efc`, direct publication, role-aware login, recommendation filtering, and
pagination. The active UI remains Django templates under `core/templates/core`;
the standalone `frontend/` directory remains a design reference.

## Retained behavior

- Proficiency stays 0–5; zero and unreported remain distinct, including resume review.
- Comparisons use `weighted_skill_match_v1` with provisional and mandatory statuses.
- Courses record interest and never award proficiency automatically.
- Active maintainers/administrators can publish complete drafts directly. Sources,
  typed requirements/mappings, expiry and revision checks still apply. Published
  editions remain immutable and publication is audited.
- Shared login honors safe `next` destinations, then sends content editors to the
  maintainer dashboard and students to their dashboard. Public registration creates
  students only; editor navigation includes Content management.

## Screens and pagination

| Feature | Routes / behavior |
| --- | --- |
| Resume import | `/resume/`, `/resume/<uuid>/review/`; PDF, DOCX or TXT, at most 2 MB; confirmation before proficiency changes |
| Private postings | POST `/postings/`, POST `/postings/<uuid>/run/`; detected catalog skills become private requirements |
| Saved progress | POST `/progress/save/`; copies reported levels and category scores |
| Skillprint | Category shape, evidence, owned skills and course selections |
| Journey | Saved progress, published-target comparisons and private-posting comparisons |
| Field Notes | Published insight cards with optional author metadata and skill tags |
| Maintainer | `/maintainer/`; existing content-management workflows retained |

### Correcting and withdrawing published content

The maintainer dashboard offers **Create successor draft** on published/retired
editions of active items, and **Retire edition** on published editions. Both routes
show a confirmation page on GET and mutate only on a CSRF-protected POST:

- `/maintainer/successor/<uuid>/` copies text, sources, details, requirements,
  learning mappings, and any Field Note metadata/tags into the same item's next
  draft. An existing draft is opened instead of creating another one. Reviews and
  publication attribution are not copied; current publication checks run again.
- `/maintainer/retire/<uuid>/` withdraws that edition and records the actor in an
  audit event. Other published editions of the item may remain available. Saved
  results retain their original editions and scores. A retired edition cannot be
  reactivated; publish a successor if it is needed again.

Existing published editions remain immutable when a successor is edited or
published. Copied sources/company records remain shared and frozen where already
published; the existing source-correction action creates a separate reference.
Expired job details or retired skill requirements may need correction in the new
draft before it can be published. These actions require a maintainer or business
administrator role, rather than Django staff/superuser flags alone.

Lists use 20 entries per page. Compare has independent `careers_page`, `jobs_page`,
and `postings_page` parameters. Journey uses `page` for reference history,
`posting_matches_page` for private history, and `snapshots_page` for saved progress.
Existing Explorer, Field Notes, Skillprint and learning-route pagination remains,
preserving filters and other list positions.

Category scores average the three strongest reported levels in each of six
categories, padded with zeros and scaled to 100. These descriptive metrics are
separate from the career/job comparison algorithm. The landing-page shape is an
example, not a student score.

Dashboard job cards show completeness and mandatory status alongside the score,
including a Provisional label for partial inputs. Progress snapshots capture skill
IDs, categories and levels in one SQL read, then derive both saved levels and
category scores from those same rows. An edit after that read cannot mix old
levels with newly computed category scores in one snapshot.

## Privacy and history

Submitting a new private posting saves the posting, detected requirements and first
comparison in one transaction. If comparison creation fails, none of those records
remain. Validation errors return the populated form for correction. Comparing an
existing posting again leaves that posting and earlier results intact on failure.

Use synthetic data for this senior-project demonstration. Uploaded files are
parsed and discarded; `ResumeImport` retains the filename, detected skill metadata,
and short text excerpts. The upload screen discloses this. Unchecked skills are
left unchanged; selected levels overwrite the corresponding owned skill/evidence.
Saving an import again is allowed and creates another progress snapshot.

Both comparison types preserve saved input/outcome data and recommendation ranks.
Private recommendations are frozen when the comparison is created rather than
recomputed on GET. Availability is checked when displaying actionable links;
withdrawn recommendations remain visible as history. Legacy private results
upgraded from the original pilot have an empty recommendation snapshot; rerun to
save recommendations rather than inventing historical ones.

Migration `pilot/0002_frozen_posting_recommendations` adds the private recommendation
snapshot and database guards for immutable private results and published Field Note
metadata/tags. Whole private-result deletion remains allowed. Draft metadata
changes advance the edition revision; the seeder attaches metadata before
publication. No existing reference tables or scoring rules are replaced.

## JSON API

The retained `/api/*` endpoints use session authentication, CSRF, ownership checks
and the shared web login-failure counter. List endpoints `/api/skills`,
`/api/me/skills` and GET `/api/comparisons` accept `page`, return the existing `data`
array, and include `pagination` with page, pages, total and has_next. The comparison
list contains reference comparisons; private comparisons can be created with
`posting_id` and opened through their owned result URL.

## Local setup and synthetic data

From the project root on Windows PowerShell, with PostgreSQL running:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\backend\manage.py migrate
.\.venv\Scripts\python.exe src\backend\manage.py seed_compass
.\.venv\Scripts\python.exe src\backend\manage.py runserver 127.0.0.1:8000
```

On macOS/Linux use `.venv/bin/python` and `src/backend/manage.py`.
`seed_compass` is optional and does not run at startup. It creates a synthetic
maintainer with an unusable password and publishes sample reference content through
the normal service. Existing content is skipped by kind/title; this is not a
generic Mockaroo importer or an upsert of published history.

Create login accounts separately with `create_demo_accounts`, which prompts for
a password and refuses to overwrite existing demo accounts. The optional
`seed_compass --demo-student EMAIL` changes that existing student's skill levels,
evidence and course selections, and creates another comparison each run. Do not
use it on an account whose current proficiency you want to preserve.

## Verification

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py check
.\.venv\Scripts\python.exe src\backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe src\backend\manage.py test core accounts skills reference comparisons auditing pilot --noinput
```

Tests use a separate database and include synthetic PDF/DOCX parsing, explicit-zero
resume review, immutable private recommendations, Field Note metadata guards,
direct publication into the student UI, API pagination and ownership boundaries.
See the [integration checklist](integration-checklist.md) for review history and
remaining coordination items.
