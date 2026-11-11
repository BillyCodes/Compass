# Branch integration checklist

Review checkpoint: November 11, 2026. This checklist records findings from the
reviewed commits; later work on those branches must be checked again. Unchecked
items are pending. Suggested owners below are coordination proposals, not
assignments agreed by the team. This document does not authorize a merge or
change existing publication rules.

## Scope and ownership

| Workstream | Reviewed commits | Suggested owner |
| --- | --- | --- |
| Student features / pilot UI | `5c3752e773a953503ca265a2342cb6ce10f6f406` | Programming lead |
| Maintainer dashboard | `4521dc0bbef6d45620e92d51311fb0f901ba5f59`, followed by `63fc59d0e237cd9fc81232c5b21930e757f2583e` | Software engineering lead |
| Integration, regression checks, setup and demo documentation | Current `Codebase-Hygiene` work | Integration owner |

Both feature branches diverge from common ancestor
`c2925c47e9817961bda688545e9b9b28ea54816f`. Their snapshots do not contain the
current branch's later setup fixes, recommendation filtering, or pagination.

The pilot commit introduces resume imports, private pasted postings, progress
snapshots, category charts, Field Note metadata, a JSON API, and synthetic seeding.
The maintainer commits introduce content-management screens and change the
database publication policy. These are functional integrations, not just UI edits.

## Shared decisions before merging

Record the chosen behavior, decision date, and agreeing reviewers for each item.

| Decision | Current behavior and branch difference | Decision record |
| --- | --- | --- |
| Independent review | Current publication requires independent approval of the exact draft revision. Maintainer migration `0008_direct_publication` removes this requirement globally, including after a reviewer requests changes. Its confirmation screen and revised tests deliberately allow direct publication. | Pending |
| Private comparison history | Reference comparisons preserve saved recommendations. Pilot `_posting_detail()` regenerates private-posting recommendations on every read. Decide whether private history has the same snapshot contract or explicitly shows current suggestions. | Pending |
| Resume proficiency | Current proficiency is 0–5, with zero distinct from unknown. Pilot review choices and `apply_import()` accept only 1–5. Define zero, unchecked skills, existing proficiency, and repeat-import behavior. | Pending |
| Resume data retention | Pilot discards the file but saves its filename and detected-skill context excerpts. Decide whether to retain excerpts, how to describe retention, and how a student removes an import. | Pending |
| Published presentation metadata | Pilot `FieldNoteProfile` author details, quotes and tags remain editable outside existing publication guards. Decide which displayed fields must be reviewed and frozen with an edition. | Pending |
| Category metrics | Pilot adds six categories and a top-three proficiency formula. Confirm the formula, category mapping, missing-input treatment, and labels; distinguish these metrics from career/job comparison scores. | Pending |
| JSON API scope | Pilot adds another registration/login/profile/comparison interface. Confirm the API is needed for the senior-project demonstration and identify who maintains its contract. | Pending |
| Synthetic content workflow | Pilot seeding creates synthetic author/reviewer accounts and publishes through services. Align this with the selected publication policy and define who owns sample data. | Pending |

- [ ] Both leads and the integration owner record the shared decisions above.
- [ ] Update architecture notes, UI wording, migrations and tests together for any
      accepted behavior change. Retain existing behavior until a change is agreed.

## Programming lead: pilot findings

- [ ] Resolve private-posting history behavior in
      `comparisons/views.py::_posting_detail()`. If recommendations are snapshots,
      save editions, ranks and explanations when creating the result; verify that
      catalog changes do not replace them when history is opened.
- [ ] Review `pilot.models.PostingMatch` integrity. It stores JSON detail and a few
      checks, but does not inherit reference comparisons' completeness and
      immutability guards. Its test named `test_match_is_frozen_and_owned` checks
      ownership but does not prove that saved rows cannot be edited.
- [ ] Reconcile level zero in `pilot/views.py::resume_review()` and
      `pilot/services/resume.py::apply_import()`. Test an existing zero proficiency
      through review and save.
- [ ] Align resume privacy wording and tests with actual retained data. The
      `detected` JSON includes nearby text from the resume; discarding the upload
      does not mean all resume text is discarded.
- [ ] Verify PDF and DOCX parsing with synthetic files, including unreadable files,
      size boundaries, and encrypted/scanned PDFs. The isolated review did not
      independently verify these formats; existing resume tests use text uploads.
- [ ] Apply the agreed review/immutability policy to Field Note metadata.
- [ ] Preserve pagination when adapting views and templates. Pilot history takes
      the latest 12 entries without navigation to older results; other lists load
      the full collection.
- [ ] Review dashboard work in `presenter.live_job_matches()` and
      `presenter.available_notes()`: these load and process whole collections
      before displaying a small subset. Verify database work with a larger
      synthetic catalog.
- [ ] If keeping the JSON API, test web/API throttle sharing, session and CSRF
      behavior, ownership, field allowlists, and bounded list responses. Keep
      authentication behavior consistent across both interfaces.

## Software engineering lead: maintainer findings

- [ ] Resolve direct publication before integrating migration
      `reference/migrations/0008_direct_publication.py`. Preserve independent
      review unless the team explicitly selects a different policy.
- [ ] Complete course details and course skill-coverage forms.
- [ ] Complete learning-resource details and skill-coverage forms.
- [ ] Verify career publication and the insight creation/source/publication flow.
      The supplied progress PDF reports these as remaining verification work.
- [ ] Verify the job flow from company creation through publication and the
      dashboard's Published status. The PDF reports this as the most complete flow.
- [ ] Remove the duplicate `edit_job_details()` definition in
      `reference/maintenance_detail_views.py`.
- [ ] Remove the duplicate publication import and URL entry in
      `reference/maintenance_urls.py`.
- [ ] Repair the unclosed Sources section opening tag in
      `reference/templates/reference/maintenance/content_form.html`.
- [ ] Add request-level tests for maintainer/administrator access, student denial,
      anonymous redirects, CSRF, POST-only removals, invalid forms, and stale draft
      revisions. The reviewed commits modify publication service tests but add no
      request tests for the maintainer screens.
- [ ] Test `edit_draft_source()` with shared published references: a correction
      must create a separate source, leave published history unchanged, and reject
      stale revisions atomically.

## Integration owner: preserve current improvements

- [ ] Confirm all intended local changes are committed before integrating; keep
      feature integration on a separate branch.
- [ ] Retain explicit virtual-environment Python paths and project-root commands
      from the current README.
- [ ] Retain recommendation filtering in PostgreSQL and its regression tests.
      Choose the latest available edition before usefulness checks so filtering
      never silently falls back to an unsuitable older edition.
- [ ] Retain the 20-entry pagination helper and shared navigation for Explorer,
      Journey, Field Notes, career/job listings, Skillprint skills/courses, and
      saved recommendations. Preserve filters and independent page parameters.
- [ ] Reconcile overlapping student views/templates as matched pairs. Pilot
      changes context shapes such as result `summary`, recommendation dictionaries,
      Skillprint groups and Field Note cards; do not mix old templates with new
      view contexts.
- [ ] Reconcile `config/urls.py` so both maintainer and retained pilot routes are
      included once. Check navigation for each business role.
- [ ] Review all migrations from the common ancestor, including policy-changing
      SQL. Verify fresh installation and upgrade of a disposable existing database.
- [ ] Retain tests that enforce unchanged rules. If a rule changes intentionally,
      document why its former regression test is replaced.
- [ ] Review the pilot's added `pypdf` and `python-docx` dependency ranges and verify
      installation in a clean environment.

## Synthetic data and demonstration

- [ ] Evaluate `pilot/management/commands/seed_compass.py` as the starting point for
      priority 5, avoiding a second importer with competing conventions.
- [ ] Keep default seeding separate from student-account setup. Document the
      synthetic author/reviewer accounts and their unusable passwords.
- [ ] Verify repeated reference seeding does not duplicate content or overwrite
      published editions. Existing checks identify content by kind/title; assess
      whether stable dataset keys are needed for changed data and title collisions.
- [ ] Document that `--demo-student` changes an existing student's proficiency and
      selections. Verify repeat behavior: its current path creates another
      comparison each run and can overwrite proficiency/evidence.
- [ ] Use synthetic records for all imports, screenshots and demonstrations.
- [ ] Write a reproducible demo: maintainer creates content, adds sources and
      requirements/mappings, completes the agreed publication flow, then a student
      reports/imports skills, compares, follows recommendations and opens history.
- [ ] Keep production hosting configuration deferred until a public demo requires it.

## Verification and merge readiness

Review evidence is specific to each snapshot, not a test of their combination:

| Snapshot | Evidence |
| --- | --- |
| Current branch with pagination | 227 tests passed during the earlier review. |
| Pilot `5c3752e` | 233 tests passed from a temporary snapshot using an isolated PostgreSQL test database. |
| Maintainer `63fc59d` | 217 tests discovered; database setup timed out before execution, including outside the sandbox. No pass result established. |

- [ ] Restore local PostgreSQL connectivity and rerun the maintainer snapshot.
- [ ] Run the complete merged suite, including `pilot` if that app is retained.
- [ ] Run Django's system check and migration consistency check.
- [ ] Verify ownership across pages: one student cannot read, change or delete
      another student's imports, postings, comparisons or snapshots.
- [ ] Verify zero versus unknown, partial/all-unreported inputs, mandatory status,
      deterministic ranking, and unchanged saved scores after proficiency edits.
- [ ] Verify publication and review behavior against the recorded team decision,
      including stale revisions, requested changes, source edits and retired skills.
- [ ] Verify withdrawn/expired content, unavailable historical recommendations,
      page boundaries, encoded filters, and access to older history.
- [ ] Exercise the full demo in a browser at desktop and mobile widths; check
      navigation, keyboard access, error messages and empty states.
- [ ] Record the final tested commit, commands/results and remaining limitations
      in the integration PR before merging.

From the project root, once the merged branch includes `pilot`:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py check
.\.venv\Scripts\python.exe src\backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe src\backend\manage.py test core accounts skills reference comparisons auditing pilot --noinput
```

On macOS/Linux, use `.venv/bin/python` and `src/backend/manage.py`. Omit `pilot`
from the test command if it is not installed. Tests create a separate PostgreSQL
test database; fresh/upgrade migration checks should use disposable databases,
not the team's application data.
