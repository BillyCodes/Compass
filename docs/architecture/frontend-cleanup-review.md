# Frontend import cleanup review

Reviewed November 3, 2026 on `integration/frontend-main`, after importing the
presentation directories from `integration/docker-test-launch` onto `main`.
This is a cleanup checkpoint before route/view integration, not a completed UI.

## Findings and safe cleanup applied

A hash scan found no byte-for-byte duplicate nonempty tracked files. The visible
redundancy is mostly two generations of presentation code, plus historical design
notes and empty directory placeholders. Backend feature apps remain the canonical
schema and business-service implementation; no pilot models or migrations were
introduced by the frontend copy.

Removed four empty `.gitkeep` files from directories that already contain tracked
files and therefore no longer need a placeholder:

- `docs/architecture/.gitkeep`
- `scripts/.gitkeep`
- `seeds/.gitkeep`
- `src/backend/accounts/templates/accounts/.gitkeep`

Removed the unused `cat_label` template filter and its unused category-label map.
The remaining nine template helpers each have references in the imported HTML.
Replaced the obsolete import of nonexistent `core.models` with the existing
`skills.models.ProficiencyLevel`; labels now follow the agreed 0–5 scale without
adding a second set of skill models or a presentation-only database enum.
The imported category-to-CSS mapping remains presentation data.

Corrected stale comments claiming publication or the account routes were still
unimplemented, updated the seed README's model status, and clarified the current
frontend checkpoint in the project and architecture documentation.

## Keep now; replace or retire after integration

| Files | Current dependency | Cleanup decision |
| --- | --- | --- |
| `src/backend/templates/base.html` and `includes/header.html`, `includes/footer.html` | Existing account login/profile templates extend/include this layout | Keep until those routes use the new design |
| `src/backend/accounts/templates/accounts/login.html`, `profile.html` | Active account views and ownership/authentication tests | Keep; restyle or replace after preserving form and route contracts |
| `src/backend/accounts/static/accounts/css/forms.css` | Existing account login template | Keep until that template no longer uses it |
| `src/backend/core/static/core/css/layout.css` | Project-level base template and foundation tests | Keep until the legacy layout is retired |
| `frontend/css/style.css` | Project-level base template loads it as `draft/css/style.css`; settings register the path | Keep; it is still an active dependency |
| `frontend/pages/*.html`, `frontend/js/data.js`, `frontend/js/main.js` | Standalone historical frontend; its own pages reference these assets; README documents previewing it | Not part of the new Django UI. Consider archiving/removing as a separate change after the team accepts the new design |
| `src/backend/core/templates/core/base.html`, `app_base.html`, `partials/logo.html` | Shared shell, authenticated shell, and reusable logo | Keep all three; parent/child composition is intentional |
| Other imported `core/*.html` templates | Planned integration targets, mostly without routes/views yet | Keep; lack of a current route does not make an imported feature screen dead code |
| `src/backend/core/static/core/compass.css` | Imported `core/base.html` | Keep; stylesheet for the new design |
| ERD PNG, draw.io file, SVGs, relationship catalog, and diagram builder | Source diagram, editable representation, generated views, and provenance | Keep; these serve different review/editing purposes |
| App `__init__.py` files, migrations, tests, and service modules | Python packages, database history, constraints, and business behavior | Keep; repeated/empty package files and historical migrations are not redundant source |
| Remaining `.gitkeep` files | Preserve intentionally empty future API/security documentation, frontend-services, and cross-app test directories | Optional later simplification if the team abandons those planned directories |

Do not delete the entire `frontend/` directory yet: its stylesheet still supports
active account pages. When retiring it later, update static settings, template
links, tests, and README preview instructions together.

No `.env`, virtual environment, database, local editor settings, or generated
static/cache directories were changed. Ignored build/cache files are not tracked
source cleanup candidates.

## Integration blockers, separate from file redundancy

The copied helper originally prevented `manage.py check` from loading the template
engine because `core.models` does not exist on this branch. That import is fixed.

The imported templates still use the pilot's unnamespaced URL names, while this
branch exposes `core:home` and the existing `accounts:*` routes. The template scan
found 22 referenced route names without matching names on this branch. These
include `home`, `login`, `dashboard`, `skillprint`, `compare`, and `result_detail`.
The imported home page currently returns HTTP 500 (`NoReverseMatch` for `home`).
Compiling templates alone cannot verify named URLs or view context at render time.
Do not add placeholder routes merely to hide this integration gap.

The existing `HomeView` supplies no pilot dashboard/catalog context. Route names,
context variables, form field contracts, ownership checks, and scoring/result
presentation need to be connected to the established backend services during the
next integration task. The old foundation home tests expect the previous layout;
update their expectations alongside the real homepage integration.

Other imported content awaiting adaptation includes the pilot's score explanation,
result terminology, category labels, and resume/Field Notes screens. Those are
integration/product mapping decisions, not justification to reintroduce the pilot
schema or delete backend services.

## Verification

- Django system checks pass after the helper cleanup.
- All 18 imported HTML templates compile, including the shared logo partial.
- The helper returns the established labels: None, Awareness, Beginner,
  Intermediate, Advanced, Expert.
- The existing account login page renders HTTP 200.
- The imported homepage is explicitly recorded as blocked by missing route names.
- Full-suite verification: 199 tests ran; 197 passed and two homepage tests
  errored with the existing missing `home` URL name. No tests were skipped or
  weakened. Migration drift check reported no changes. Verification used an
  isolated temporary PostgreSQL container, which was removed afterward; the
  application database was untouched. A clean system check is not a claim of
  completed route integration.

## Recommended cleanup order

1. Keep this limited cleanup separate from integration changes.
2. Integrate the new shared layout, home, sign-in, and owned profile routes.
3. Connect skill entry, target selection, saved comparisons, and recommendations
   to their existing feature services; preserve permissions and audit behavior.
4. After the account routes use the accepted layout, remove the legacy templates,
   includes, and styles only after a fresh reference search finds no dependents.
5. Decide whether to archive the standalone draft and remove genuinely unused
   styles/helpers after all retained screens have been exercised.
