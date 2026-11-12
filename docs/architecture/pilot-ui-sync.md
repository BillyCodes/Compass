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

Course choices, selection validation, selected-course cards, and recommendation
generation share the same learning-edition policy. Select the latest published,
unexpired edition of an active item, then reject editions with retired skill
mappings. Withdrawing that edition permits an older available published edition;
an ineligible newer published edition does not silently fall back. Existing
selections remain readable as unavailable history when no eligible edition exists.
Detail links and saved recommendation links validate their exact edition with
the same publication, expiry, item and skill checks, preserving eligible older
editions referenced by history. Course selection never awards proficiency.

Skillprint category scores describe all reported skills. When its skill list spans
multiple pages, empty category sections say there are no skills on the current
page rather than implying the student has never reported skills in that category.

Category scores average up to three strongest reported levels in each of six
categories, without padding missing slots, and scale to 100. One Advanced skill
scores 80; no reported skills scores zero. These descriptive metrics are
separate from the career/job comparison algorithm. The landing-page shape is an
example, not a student score.

The UI updates from `9e13bed`, `2781a05` and `6e07653` add About Compass copy and
the revised category scale. Publication wording reflects maintainers publishing
directly with sources, and the Skillprint explanation distinguishes reported
proficiency from career readiness.

Migration `pilot/0003_progress_snapshot_scoring_version` labels existing saves
`padded_top3_v1` without changing their scores or skill inputs. New saves (including
synthetic history generated by the seeder) use `reported_top3_v2`. Dashboard and
Skillprint overlays use the latest save only if its formula matches the current
one. Journey overlays use the oldest current-formula save; its timeline retains
and labels older saves, comparing category deltas only between adjacent saves
with the same formula, including across page boundaries. Career/job readiness and
skill-level improvement counts retain their existing calculation.

Dashboard job cards show completeness and mandatory status alongside the score,
including a Provisional label for partial inputs. Progress snapshots capture skill
IDs, categories and levels in one SQL read, then derive both saved levels and
category scores from those same rows. An edit after that read cannot mix old
levels with newly computed category scores in one snapshot.

Dashboard job matching selects the latest available editions first, filters out
jobs with no reported relevant skills, and ranks weighted scores in PostgreSQL.
Only the top three editions and their requirements are loaded for the shared
Python scorer to build cards. Selection uses rounded scores and stable item-ID
ties, preserving the previous ranking and all completeness/mandatory labels.
This uses three queries when matches exist, one when none are eligible, and no
queries for an empty Skillprint. Database ranking still scales with eligible
requirements; application memory and Python scoring are limited to the winners.
Regression tests compare SQL selection against `weighted_skill_match_v1`, including
rounding, explicit zeros, unknowns and edition availability. Any future scoring
algorithm change must update this SQL selection and its parity tests together.

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
