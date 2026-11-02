# Reference data, details, requirements, and learning mappings

Implemented November 1, 2026 as the second reference database batch. This extends
[the skills/item/version foundation](skills-reference-foundation.md) with six
reference tables. It does not add publication, comparison scoring, or new screens.

## Tables and ERD mappings

| Table | Django model | Relationship and purpose |
| --- | --- | --- |
| `company` | `reference.Company` | Organization reference data; no employer account or login |
| `reference_source` | `reference.ReferenceSource` | Source title, URL or textual identifier, and collection timestamp |
| `content_source` | `reference.ContentSource` | Many-to-many version/source association; unique `(version_id, source_id)` |
| `content_requirement` | `reference.ContentRequirement` | A skill requirement for one career/job version; unique `(version_id, skill_id)` |
| `content_skill` | `reference.ContentSkill` | Learning coverage for one course/resource version and skill; unique `(version_id, skill_id)` |
| `content_details` | `reference.ContentDetails` | Zero or one type-specific details row per version; `version_id` is PK and FK |

The join models use surrogate UUIDs (`source_link_id`, `requirement_id`, and
`mapping_id`) plus logical-pair unique constraints, consistent with the existing
Django-friendly account-role mapping. The one-to-one details row needs no extra ID.
No second credential store, employee/employer identity, or new permissions system
has been introduced.

## Typed relationships and validation

The requirement, coverage, and details models retain ordinary Django version FKs
for ORM navigation. Migration `reference/0004_typed_reference_foreign_keys.py`
adds explicit PostgreSQL composite FKs for each:

```text
child(version_id, kind) -> content_version(version_id, kind)
```

These constraints are deferrable, initially immediate, reversible, and enforce
kind agreement even on direct database writes. Local CHECKs further restrict
requirements to career/job kinds and coverage mappings to course/resource kinds.
Maintain these SQL constraints explicitly when changing related schema fields;
Django does not infer multi-column FKs from ordinary relation fields.

Both `required_level` and `coverage_level` use the agreed integer scale:
0 none, 1 awareness, 2 beginner, 3 intermediate, 4 advanced, 5 expert. Model choices,
database bounds, and service validation enforce that scale. Evidence of course
coverage does not automatically create or increase private student proficiency.

Requirement weights are finite nonnegative decimals (10 digits, 4 decimal places).
Zero is permitted for a draft requirement; rejecting an all-zero published target
belongs to the later publication workflow. This batch does not select a scoring
formula, mandatory-skill policy, or treatment of absent student inputs.

## Optional details by kind

| Fields | Permitted kind |
| --- | --- |
| `company`, `location`, `expires_at` | job |
| `course_code`, `credits` | course |
| `provider`, `resource_url`, `cost_amount`, `currency` | course or resource |

Other kinds can have an empty optional details row. These restrictions are enforced
by database CHECKs as well as model validation. Publication-specific requirements
(such as whether a job needs a company or a resource needs a URL) remain pending.
The company FK is optional; a company can be referenced by many job detail rows.

Credits are optional finite nonnegative decimals with 5 digits/2 decimal places;
costs are optional finite nonnegative decimals with 12 digits/2 decimal places.
Explicit upper bounds in the CHECKs reject PostgreSQL numeric NaN as well as
negative values, including when Django validation is bypassed.

A supplied cost, including zero, requires a three-uppercase-letter currency;
absent cost requires blank currency. Services normalize currency to uppercase.
This checks the code's format, not membership in a maintained currency registry,
and performs no currency conversion.

The resource URL is validated as HTTP/HTTPS by Django. A source identifier can
instead be a non-URL bibliographic/dataset identifier. Neither service fetches
URLs or uploads files. Optional text uses empty strings; optional numeric/date/FK
values use NULL. Blank collection dates default to the current time when omitted.

## Authorized draft operations

All new services require an active Compass maintainer or administrator business
role. Student, anonymous, disabled, and staff/superuser-only accounts cannot use
these editor operations. Existing student authentication/ownership rules remain.

- `create_company` and `create_reference_source` create validated reference rows.
  They do not provide global updates to records already cited elsewhere.
- `attach_source` links an existing source; a duplicate attachment is a no-op.
- `set_requirement` creates or updates one career/job version/skill pair.
- `set_skill_mapping` creates or updates one course/resource version/skill pair.
- `set_content_details` replaces the complete details state. Omitted optional
  fields are cleared; callers must send the full desired details state.
- `detach_source`, `remove_requirement`, `remove_skill_mapping`, and
  `clear_content_details` remove related data from drafts only.

Every version-related mutation requires `expected_revision`, locks the version,
rejects non-drafts and retired parent items, and increments the draft revision
within the same transaction after a successful change. A stale or invalid input
leaves rows and revision unchanged. No-op attachment/removal does not bump the
revision. Requirements and learning mappings also reject retired skills.

This revision policy prepares for exact-draft approval invalidation. **It does not
implement review or publication approval yet.** Existing foundation text edits
now use the same draft guard. There are no new HTTP endpoints, admin registrations,
or unguarded publication services in this batch.

## Deletion and history

Sources, versions, companies, and skills use protected relationships while they
are referenced. Draft links/details can be removed through the guarded services
before deliberate cleanup; shared reference rows are not cascade-deleted with a
student. Published/retired versions cannot be changed by these services.

Direct ORM/SQL access is trusted developer access. Database constraints enforce
relational integrity, type applicability, bounds, and uniqueness; they do not yet
freeze all published history or enforce review approval. The later publication
milestone must address all write paths, including shared source/company metadata.

## Migrations and testing

```sh
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py test core accounts skills reference
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
```

Added migrations:

- `reference/0003_company_referencesource_contentdetails_and_more.py`: six tables
  and their local/unique constraints.
- `reference/0004_typed_reference_foreign_keys.py`: three multi-column FKs.

The full suite now contains 92 PostgreSQL-backed/account/foundation tests. New
checks include typed references on direct writes, all six level values, unique
pairs, source sharing, one-to-one details, numeric NaN rejection, applicability
and currency rules, role restrictions, draft revisions, stale/invalid rollback,
protected deletion, and rejection of all service edits to non-draft versions.
Tests initialize an isolated database from migrations.

No production credentials, synthetic domain rows, or new accounts are seeded by
these schema migrations. After applying, refresh `compass` -> `public` -> Tables
in the PostgreSQL extension to inspect the six additional tables.

## Next batch

Student course selections and version-specific content reviews can now be added.
Review/publication needs current-revision approval, sources and type-specific
completeness checks, publication authority, and immutable published content. The
comparison/result/recommendation/audit tables follow that lifecycle work.
