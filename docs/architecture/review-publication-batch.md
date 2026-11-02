# Student courses and reference review/publication

Implemented November 1, 2026. This batch adds `student_course`, `content_review`,
and PostgreSQL row-level integrity guards for the reference lifecycle. It extends
[reference-data batch two](reference-data-batch.md); comparisons and audit events
remain the next database section. No new HTTP screens or admin routes are added.

## Confirmed authorization policy

The team selected these rules:

- Active Compass maintainers and administrators may review and publish content.
- A reviewer must be a different **account** from the version's author.
- An author may publish after another eligible account approves the current draft.
  The publisher does not need to be a third account.
- Django staff/superuser flags alone do not grant these business capabilities.

Independent accounts support separation of duties; the application does not prove
that two accounts are operated by different human beings. Existing demo account
roles are unchanged. A local publication demonstration needs two deliberately
provisioned eligible accounts; this migration creates neither accounts nor grants.

## New tables and physical mapping

| ERD entity | Django model | Mapping |
| --- | --- | --- |
| STUDENT_COURSE | `skills.StudentCourse` | UUID `selection_id` plus unique `(student_id, course_item_id)` |
| CONTENT_REVIEW | `reference.ContentReview` | UUID `review_id`, version/reviewer FKs, `reviewed_revision`, decision, time, plain-text note |

STUDENT_COURSE points to the stable CONTENT_ITEM identity. A composite FK on
`(course_item_id, course_kind)` targets `(item_id, kind)`, and a local CHECK fixes
course_kind to `course`. Student deletion cascades private selections; selected
shared course identities are protected from deletion.

CONTENT_REVIEW uses the corrected field name `reviewed_revision`, not the ambiguous
`reviewed_version`. It refers to a draft revision of a particular CONTENT_VERSION,
not to the item's public `version_no`. Review revision must be positive; decisions
are `approved` or `changes_requested`. Version and reviewer deletion are protected.
Reviews are append-only: submit another decision rather than editing/deleting one.

## Private course selection

Services in `skills/services.py`:

- `select_student_course(actor=..., course_item_id=...)`
- `list_student_courses(actor=...)`
- `remove_student_course(actor=..., course_item_id=...)`

They derive ownership from an active account with a student role and profile,
never a caller-supplied student ID. Selection is idempotent per student/course.
New selections require a non-retired course item with a published version.
Existing selections remain when a version or item is retired, and students may
remove their own historical selections. Maintainers without student roles/profiles
cannot act as students through these services.

Selection is not enrollment, a completed course, an assessment, or proof of skill.
No proficiency is automatically added or changed. Selecting an item also does not
pin a scoring input version; coursework affecting scores would need separate,
versioned input snapshots in the later comparison design.

The typed FK protects ordinary database writes from referencing a job/career item.
Availability and owner authorization are application-service checks, not PostgreSQL
row-level security. Future views must pass `request.user` as actor.

## Review and publication services

`reference/services.py` now provides:

- `review_content_version(actor, version_id, expected_revision, decision, review_note)`
- `publish_content_version(actor, version_id, expected_revision)`
- `retire_content_version(actor, version_id)`
- `available_content_versions(kind=None)`

The signatures use keyword arguments. Reviews and publication lock the version
and validate the caller's expected revision. Reviews do not modify the content
revision. They record the exact current revision and enforce strictly increasing
decision timestamps for that revision, even if the application clock repeats a
microsecond. The latest decision for the current revision is authoritative: a
later changes-requested review blocks an older approval. Later approval can clear
that block without overwriting history.

Publishing requires the latest decision to be independent approval, with its
reviewer still active and holding an eligible role. Editing content after approval
requires a new review. Publication records the actor and timestamp atomically.
Failed publication leaves the version a draft without publication attribution.

## Initial publication completeness rules

| Kind | Required before publication |
| --- | --- |
| All kinds | Meaningful title/body, at least one source with a meaningful title/identifier, current independent approval, active publisher, non-retired item |
| career/job | At least one skill requirement with positive weight; all referenced skills active |
| course/resource | At least one positive coverage mapping; all referenced skills active |
| course | Details containing a course code or provider |
| resource | Details containing an HTTP/HTTPS resource URL; the service revalidates full URL syntax |
| job | Must not have an expiry at or before publication; company remains optional |
| insight | The common rules; no artificial skill-mapping requirement |

These are the initial application rules, not a scoring formula. An explicit zero
weight/level can exist in drafts, but an all-zero-weight career/job target or an
all-zero-coverage learning version cannot be published. Required/coverage levels
retain the agreed 0–5 scale. Comparison treatment of missing inputs and mandatory
requirements remains to be implemented in the scoring milestone.

The PostgreSQL publication trigger is the authoritative shared gate for approval,
roles, sources, type-specific minimum completeness, and attribution. The Django
service additionally validates details, including complete URL syntax, and returns
friendly validation errors for rejected transitions. A raw SQL HTTP prefix alone
is not equivalent to Django's full URL validation. No URL is fetched.

## Revision and published-history guards

Migration `reference/0006_publication_guards.py` installs eight row triggers and
supporting functions:

1. Versions start as unpublished drafts. Identity/authorship cannot be reassigned.
   Direct draft title/body edits advance the revision. Services retain optimistic
   revision checks for request-level lost-update protection.
2. Any requirement, mapping, details, or source-link insert/update/delete advances
   its draft version's revision in the same transaction. Related rows cannot be
   moved to another version. SQL writes therefore invalidate old approval too.
3. Editing a source/company used by drafts advances every affected draft revision.
   Shared rows referenced by published/retired content cannot be changed/deleted.
   Make a new reference row and a successor draft for corrected metadata.
4. Reviews require an active eligible independent account, a current draft/revision,
   and a non-retired item. Existing reviews cannot be updated or deleted.
5. Publication checks current policy. Published core content, source links,
   requirements, mappings, details, and attribution are frozen. Retirement changes
   only availability/status and preserves history; it cannot restore a retired
   version to published or draft. Corrections use a successor version number.

Child-data triggers now increment revisions, so the Python `_touch_revision` helper
refreshes the database value rather than incrementing a second time. Apply the
migrations before using the new services. Existing source/mapping service contracts
and expected revision counts remain compatible.

Database row locks serialize publication with competing related/source edits.
The tests use separate PostgreSQL connections to check rejected concurrent edits
and unique sequential version allocation. These locks/constraints protect ordinary
row writes, not privileged administrators deliberately disabling triggers, changing
DDL, or truncating tables. Do not treat them as an external tamper-proof audit log.

## Retirement and public availability

Retiring a published version retains its content, children, reviews, and publication
attribution. New drafts can be created on the same non-retired item as successor
versions, with fresh reviews and no copied approval. A retired item prevents new
versions and draft edits. `available_content_versions` filters to published status,
non-retired items, and non-expired details; it never returns drafts or retired
versions. Future comparison services must additionally validate applicable current
requirements when a comparison is requested.

## Migrations and verification

```sh
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py test core accounts skills reference
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
```

- `reference/0005_contentreview.py`: review history and local constraints/index.
- `reference/0006_publication_guards.py`: reversible PostgreSQL lifecycle guards.
- `skills/0002_studentcourse.py`: private selected-course records.
- `skills/0003_student_course_kind_foreign_key.py`: typed course identity FK.

The full suite now has 136 tests. It covers authentication, prior schema batches,
course ownership/availability, independent/latest/current-revision review, all five
publication kinds, validation failures and rollback, direct-write invalidation,
immutability, shared-reference protection, retirement, concurrency, and reversal/
reinstallation of the custom guard migration in the isolated test database.

The two new tables begin empty. Existing application record counts are verified
before/after migration. No production or demo content is automatically published,
and no privileged account is created. Refresh `compass` -> `public` -> Tables in
the PostgreSQL extension to see the new tables.

## Next section

The [comparison batch](comparison-batch.md) now implements comparison results,
skill input snapshots, per-skill outcomes, and recommendations. Audit events remain. The [comparison scoring rules](comparison-scoring.md)
now record the agreed score calculation, mandatory-skill semantics, and
missing-input treatment for implementing comparison services. New forms
and management screens can then call the tested backend services without bypassing
ownership, revision, review, or publication checks.
