# Skills and reference-content foundation

Implemented November 1, 2026 after approval of the relationship corrections.
This batch adds four models and their validated service operations. It does not
implement the remaining ERD, publication workflow, or new web pages.

Update: [the next reference data batch](reference-data-batch.md) is now implemented.
This note retains the first batch's scope and original verification count.

## Implemented tables

| Table | Django model | Purpose and relationship |
| --- | --- | --- |
| `skill` | `skills.Skill` | Shared skill vocabulary; unique name, optional category, active/retired status |
| `student_skill` | `skills.StudentSkill` | Private current self-reported proficiency for one student and one skill |
| `content_item` | `reference.ContentItem` | Stable identity for a career, job, course, resource, or insight |
| `content_version` | `reference.ContentVersion` | A numbered edition of that item, with draft revision and account attribution |

Application source lives in `src/backend/skills/` and `src/backend/reference/`.
Both apps are registered in settings. New HTTP routes and admin model screens
are deliberately not introduced in this database-foundation batch.

## Agreed proficiency scale

| Value | Label |
| --- | --- |
| 0 | None |
| 1 | Awareness |
| 2 | Beginner |
| 3 | Intermediate |
| 4 | Advanced |
| 5 | Expert |

`skills.models.ProficiencyLevel` is the shared vocabulary for later compatible
requirement, coverage, and input-snapshot fields. A database CHECK bounds student
proficiency to 0..5; service validation also rejects fractional, boolean, string,
and missing values rather than coercing them into integers.

An explicit level 0 and no STUDENT_SKILL row are different stored states: "none"
versus "not supplied." Define the scoring treatment of absent inputs before
comparison implementation. Self-reported proficiency is not verified mastery;
course coverage will not automatically raise a student's level.

## Student skills and access

STUDENT_SKILL has a surrogate UUID `student_skill_id`, with unique `(student_id,
skill_id)` preserving the logical ERD identity. It links to the existing student
profile and protects referenced skills from deletion. Deleting a student removes
that student's private proficiency rows. Optional evidence is plain text stored
as an empty string when absent; no uploads, rendering as HTML, or verification
process are implemented.

`set_student_skill(actor=..., skill_id=..., proficiency_level=..., evidence_text=...)`
resolves the student from an active signed-in account with the student business
role. It accepts no caller-supplied student ID. Repeated writes update the same
logical pair rather than creating duplicates. The operation locks the skill row
while checking retirement and saving the record.

`list_student_skills(actor=...)` returns only that account's student records.
These are backend service contracts; future views must pass `request.user` as the
actor and must preserve ownership filtering.

Catalog creation and retirement require a maintainer or administrator Compass
role. A Django staff/superuser flag alone is not sufficient. Retirement preserves
existing proficiency records but blocks further student edits to that skill.
Skill names are trimmed by the creation service, and unique according to the
ordinary database text comparison; no new case-insensitive skill-name policy has
been introduced. Category/evidence follow Django's optional-text convention.

## Reference identity and versioning

An item may have no versions while being prepared, and may later have multiple
versions of its one fixed kind. There is intentionally **no** unique constraint
on `(item_id, kind)` in CONTENT_VERSION. The version-number uniqueness is
`(item_id, version_no)` instead.

The parent item has a unique `(item_id, kind)` candidate key. The version has
both the ordinary Django `item` FK and an additional PostgreSQL composite FK:

```text
content_version(item_id, kind)
    -> content_item(item_id, kind)
```

`reference/0002_item_kind_foreign_key.py` installs that constraint with reversible
`RunSQL`. It is deferrable but initially immediate. Ordinary writes cannot attach
a course version to a career item, or change a referenced parent kind underneath
its versions. The existing ordinary FK provides Django's ORM relation; the extra
constraint supplies the cross-column integrity rule. A unique `(version_id, kind)`
key is also ready as the target for later typed references.

The composite FK has no equivalent auto-generated model-state operation. Preserve
and review its migration explicitly when changing related fields. These migrations
require PostgreSQL; an SQLite-only test run does not verify this design.

## Draft service operations

- `create_content_item(actor=..., kind=...)` validates an allowed content kind.
- `create_draft_version(actor=..., item_id=..., title=..., body=...)` derives the
  kind from the item and assigns the next version number while locking its parent.
  Retired items cannot receive new versions. Title and body must be nonempty.
- `update_draft_version(actor=..., version_id=..., expected_revision=..., title=...,
  body=...)` permits only draft edits, increments the draft revision, and rejects
  stale revision submissions. The version row is locked while editing.

All three operations require a maintainer or administrator business role. Authors
are derived from the actor. Creator and optional publisher references use PROTECT;
attributed accounts need deliberate deactivation/anonymization rather than an
unreviewed deletion.

The model includes draft/published/retired statuses for the agreed schema, checks
positive version/revision numbers, and requires paired publisher/timestamp values
and attribution for a published status. The exposed services create/edit drafts
only. **Publication is not implemented or authorized by those metadata checks.**

Source/requirement/detail/coverage models now exist in the second batch. Review
approval, publication validation, published-content immutability across all write
paths, and retirement workflows remain subsequent milestones. Direct ORM/SQL access
is trusted developer access; do not use it to simulate an approved publication.
No public reference browsing or publication API is introduced here.

## Migrations and verification

```sh
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py test core accounts skills reference
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
```

Added migrations:

- `skills/0001_initial.py`: skill catalog and student proficiency constraints.
- `reference/0001_initial.py`: content item/version models and local constraints.
- `reference/0002_item_kind_foreign_key.py`: database-enforced kind consistency.

The 61-test suite includes the original 28 account/foundation checks plus 33 new
checks of validation, role access, student ownership, retirement/deletion behavior,
version-number uniqueness, draft revisions, attribution metadata, and direct-write
kind enforcement. The test database is created from migrations on PostgreSQL.

The initial application of these migrations preserved existing account/profile/
role record counts and left all four new tables empty. No domain data, privileged
accounts, or new login credentials were automatically inserted.

To inspect the new schema in the VS Code PostgreSQL extension, refresh the
`compass` database's `public` tables. For a read-only schema check:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('skill', 'student_skill', 'content_item', 'content_version')
ORDER BY table_name;
```

## Next implementation batches

1. Sources, companies, details, requirements, and course/resource skill mappings
   are now implemented in the linked second batch.
2. Add student course selections and exact-draft review/publication rules.
3. Add comparison inputs/outcomes, recommendations, and minimal audit events with
   same-target integrity and server-side scoring.
4. Connect forms/screens to the tested services in coordination with the
   programming lead's frontend. The services already expose ownership boundaries.
