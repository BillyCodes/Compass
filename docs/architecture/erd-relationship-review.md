# Final-draft ERD review and proposed relationship completion

Reviewed November 1, 2026 against `Compass ERD Final Draft.png` and the implemented
Django account models. The image is reference material, not an instruction to
execute migrations. This review adds design artifacts only; it does not change
models, migration history, existing data, or application behavior.

Implementation update: the following [foundation batch](skills-reference-foundation.md)
and subsequent reference/review batches now implement all A1–A8 and R1–R13
relationships. The [comparison batch](comparison-batch.md) now implements C1–C9.
The [audit batch](audit-batch.md) now implements D1–D3, completing the planned schema.
The approved proficiency scale is 0–5. The original review diagrams/catalog retain
their proposal-snapshot labels; consult the foundation note for current coverage.

## Assessment

The draft is consistent with the established direction: separate accounts and
student profiles, explicit role assignments, private student inputs, versioned
career/job reference content, reproducible comparisons, and minimal audit events.
It is a useful implementation guide once relationship direction, optionality,
and the constraints below are clarified.

The account section is logically aligned with Django. Its remaining differences
are already deliberate physical mappings:

| Draft | Implemented Django model |
| --- | --- |
| ACCOUNT.status active/disabled | `Account.is_active` boolean |
| ACCOUNT.password_hash | Django's `password` attribute stored in the `password_hash` column |
| ACCOUNT_ROLE composite primary key | UUID `assignment_id` primary key plus unique `(account_id, role_id)` |
| STUDENT optional text fields nullable | `major` and `career_interests` use empty strings for optional text |
| Account/student UUIDs and timestamps | Already implemented |
| `assigned_by` nullable account reference | Already implemented; physical column is `assigned_by_id` |

Do not replace the working account models just to make the picture's column names
literal. See [the first-section mapping](erd-django-mapping.md). Django framework
tables belong in a physical-schema appendix, not among the new domain entities.

## Deliverables and notation

- [Editable draw.io diagram](<Compass ERD Relationships.drawio>): seven focused
  relationship views. Open with diagrams.net/draw.io; each view is a separate tab.
- [Complete relationship catalog](erd-relations/relationships.md): 33 named links,
  foreign keys, cardinalities, and proposed deletion behavior, including one
  explicitly redundant direct skill link (C7).
- SVG previews are embedded in that catalog and can be opened separately.
- [Diagram builder](../../scripts/build_erd_relationships.py) regenerates the
  relationship views with Python's standard library, without database access.

Each view shows relationship-relevant fields, not every non-key attribute. The
original PNG remains the full-attribute draft and is unchanged. Repeated entity
boxes across views refer to the same table. The two ACCOUNT boxes in the audit
view are actor and subject aliases of that one table.

Endpoint counts are explicit rather than relying on the incomplete crow's-foot
connectors in the original: `1` = exactly one, `0..1` = optional one, `0..*` = zero
or many. Counts next to an entity say how many of that entity can be related to
one entity at the other end. Crossing lines are not additional relationships.

A1-A4 are implemented relationships. The other 29 catalog entries are design
proposals, including the redundant C7 link. Deletion rules outside A1-A4 are also
proposals for review, not applied database policies.

## Corrections to make in the full-attribute draft

### 1. Fix content version uniqueness

Remove `UNIQUE(item_id, kind)` from **CONTENT_VERSION**. All versions of one item
share its kind, so this would limit that item to a single version. For example,
career item X could not have both version 1 and version 2.

Keep:

- `CONTENT_ITEM.item_id` as the primary key.
- `CONTENT_ITEM UNIQUE(item_id, kind)` as the composite FK target.
- `CONTENT_VERSION UNIQUE(item_id, version_no)` to prevent duplicate version numbers.
- `CONTENT_VERSION UNIQUE(version_id, kind)` as the typed-version FK target.
- `CONTENT_VERSION (item_id, kind)` as a **foreign key**, not a unique key, to
  `CONTENT_ITEM(item_id, kind)`.

The parent-to-version relationship is one item to zero or many versions (R1).
Draft items may initially have no versions; an available published item must have
an available published version. Item kind should not be changed underneath history.

### 2. Correct details and company cardinalities

`CONTENT_DETAILS.version_id` is both PK and FK in the draft. Consequently, one
CONTENT_VERSION has zero or one CONTENT_DETAILS row, and every details row belongs
to exactly one version (R12). Draw a one-to-one optional connector, not a many end.

`CONTENT_DETAILS.company_id` is nullable: each details row has zero or one company,
while a company can be referenced by zero or many details rows (R13). The original
connector's many end appears next to COMPANY; move the many end to CONTENT_DETAILS.

Replace the vague `CONTENT_DETAILS.kind = content` description with the actual
allowed content kinds and require agreement with its parent version. Proposed
business rule: `company_id` is used for job details and is empty for other kinds.
A job without an identified company can still have NULL here. The team should
confirm this type-specific rule; it is not needed to finish account authentication.

### 3. Draw the account attribution and audit links separately

Add or explicitly label these account references:

- ACCOUNT -> CONTENT_VERSION.created_by: each version has exactly one creator.
- ACCOUNT -> CONTENT_VERSION.published_by: zero or one publisher per version;
  NULL for an unpublished draft, required on publication.
- ACCOUNT -> CONTENT_REVIEW.reviewer_id: each review has exactly one reviewer.
- ACCOUNT -> AUDIT_EVENT.actor_account_id: zero or one actor per event.
- ACCOUNT -> AUDIT_EVENT.subject_account_id: zero or one affected account per event.
- CONTENT_VERSION -> AUDIT_EVENT.content_version_id: zero or one referenced version
  per event.

Each account or version can appear in zero or many corresponding records. These
are separate foreign keys even when they point to the same table. Audit actor and
subject are not always the same person; anonymous/system events can lack an actor.
AUDIT_EVENT should require `event_type` and `occurred_at`, with controlled event
names and minimal metadata. It is not a duplicate of `django_admin_log`.

### 4. Make every typed content link enforceable

An ordinary `version_id` FK guarantees that a version exists. It does not guarantee
that a career comparison targets a career/job or that a recommendation targets a
course/resource. The duplicated kind fields need real consistency enforcement.

| Referencing row | Required typed reference | Allowed kind |
| --- | --- | --- |
| STUDENT_COURSE | `(course_item_id, course_kind)` -> CONTENT_ITEM `(item_id, kind)` | course only |
| CONTENT_VERSION | `(item_id, kind)` -> CONTENT_ITEM `(item_id, kind)` | all five content kinds |
| CONTENT_REQUIREMENT | `(version_id, kind)` -> CONTENT_VERSION `(version_id, kind)` | career, job |
| CONTENT_SKILL | `(version_id, kind)` -> CONTENT_VERSION `(version_id, kind)` | course, resource |
| CONTENT_DETAILS | `(version_id, kind)` -> CONTENT_VERSION `(version_id, kind)` | actual parent kind |
| MATCH_RESULT | `(target_version_id, target_kind)` -> CONTENT_VERSION `(version_id, kind)` | career, job |
| RECOMMENDATION | `(resource_version_id, resource_kind)` -> CONTENT_VERSION `(version_id, kind)` | course, resource |

Use matching-kind composite FKs plus local allowed-kind CHECKs in a physical schema
that retains this typed design. Merely listing two ordinary FKs, adding a kind
choice field, or putting `clean()` on the model does not provide the same guarantee.

These are the typed endpoints captured in A8, R1, R6, R8, R12, C2, and C9. There
is no relationship from an arbitrary STUDENT_COURSE row to an arbitrary job item.

### 5. Connect outcomes to the exact matched requirement

MATCH_SKILL_RESULT needs both composite relationships already named in the draft:

1. `(match_id, target_version_id)` -> MATCH_RESULT `(match_id, target_version_id)`.
2. `(target_version_id, skill_id)` -> CONTENT_REQUIREMENT `(version_id, skill_id)`.

Together, they prevent a result for career version X from reporting an outcome for
a requirement belonging to version Y. Draw the second connector to
**CONTENT_REQUIREMENT**, not just SKILL or CONTENT_VERSION.

Keep MATCH_RESULT's unique `(match_id, target_version_id)` as a composite-FK target,
even though match_id alone is a primary key. Keep one outcome per `(match_id,
skill_id)`. A requirement can appear in outcomes for many different comparisons.

The direct MATCH_SKILL_RESULT.skill_id -> SKILL FK (C7) is logically redundant if
the requirement FK and its skill FK are enforced. It is shown because the draft
labels that field as a direct FK; it may be removed to simplify the physical
schema, with no loss of the skill association through CONTENT_REQUIREMENT.

### 6. Keep selected courses and result snapshots distinct

STUDENT_COURSE points to a stable course CONTENT_ITEM. This is reasonable while it
means "selected course" rather than enrollment history or a scoring input. It
must have unique `(student_id, course_item_id)`. A repeatable enrollment/history
feature would need additional identity and dates.

MATCH_INPUT_SKILL points to MATCH_RESULT and SKILL, not the mutable STUDENT_SKILL
row. Save the level actually used, and define how missing skills are represented
(for example, an explicit zero or absence with a documented meaning). Editing a
current proficiency must not change an old comparison.

If courses later affect scoring, pin the relevant course/mapping versions and
snapshot the scoring inputs too. Current course selection alone must not silently
increase a student's verified proficiency.

### 7. Make review approval specific to a draft revision

The draft has `CONTENT_VERSION.draft_revision` but `CONTENT_REVIEW.reviewed_version`.
Rename the latter to `reviewed_revision` (or `reviewed_draft_revision`) so it cannot
be confused with the published `version_no`.

A review belongs to one version (R4), and one account performs it (R5). At
publication, an approved review must match both the exact version ID and current
draft revision. Editing a draft increments the revision and invalidates older
approval. Approval matching is a transactional publication rule, not a new FK to
a mutable draft_revision value that would prevent future edits.

Published content, requirements, skill mappings, and source links become immutable.
Corrections create successor versions. Retirement changes availability without
rewriting historical content. Publication authorization must check the relevant
business role/permission; a reviewer FK alone proves no authorization.

## Cardinality versus lifecycle rules

The diagrams generally allow zero child records so drafts, unused skills, and
new reference rows can exist. This does not mean an incomplete career profile may
be published or an incomplete match may be saved as successful.

Before publication, require valid career/job requirements with at least one
positive weight, the current approved review, sufficient sources, type-specific
fields, and publisher/time attribution. Other kinds have their own requirements.
Before saving a completed match, require one outcome for each applicable target
requirement, a consistent input snapshot, and the server-calculated score. Save
these private result records atomically. Recommendations remain optional.

Add local bounds/checks for version_no > 0, draft/review revision > 0, score in
0..100, weight >= 0, priority_rank > 0, and nonnegative costs/credits where used.
The skill scale and mandatory-skill/scoring rules remain team decisions; apply the
same agreed scale to proficiency_level, required_level, coverage_level, and
level_used where their meanings are compatible.

`MATCH_RESULT.alg_version` should be required. A text version can suffice initially
if it resolves to retained calculation code and configuration. A scoring-rule
version table is an optional later refinement, not an entity silently added here.
CONTENT_SOURCE supports version-level provenance; if individual requirements need
separate evidence attribution, extend that relationship deliberately before
claiming per-requirement provenance. Optional saved AI explanations are not shown
in this supplied draft and are not added by this review.

## Deletion and retention proposal

A1-A4 retain the implemented behavior: account-to-student and recipient assignment
CASCADE, referenced role PROTECT, and assigner SET_NULL.

For new shared reference rows, prefer PROTECT/retirement rather than cascading
deletions through compared versions, historical requirements, sources, and
recommendations. Creator/reviewer/publisher attribution is proposed as PROTECT;
this means an attributed account must be disabled or handled through an approved
anonymization workflow rather than simply deleted. Published versions must not
lose required publisher attribution through an automatic SET_NULL.

Private results and their input snapshots, outcomes, and recommendations need an
explicit student-data deletion workflow. Cascading those private children with a
result can be appropriate; shared reference content must survive that deletion.

Nullable audit links can use SET_NULL to preserve minimal events without keeping
a whole account or content row forever. Event-retention periods and what minimal
attribution is required still need team agreement. Deleting a FK target does not
make arbitrary personal information stored in audit metadata safe to retain.

## Django implementation choices to settle before migrations

The logical relationships above should not be mistaken for already generated
Django constraints. Django 6.1 has composite-primary-key support, but ordinary
ForeignKey relationships to composite-key models and admin support remain limited.
A normal ForeignKey plus a UniqueConstraint does not automatically implement a
multi-column FK to another table.

Continue the practical convention already used for ACCOUNT_ROLE: use surrogate
UUID primary keys for join entities where useful, plus unique constraints on the
logical pairs. For the typed/same-target invariants, choose an explicit strategy:

- Retain the proposed shared typed-content design and add reviewed PostgreSQL
  composite FKs with migrations that coordinate database state and Django state.
- Or revise the physical model into clearer subtype/explicit association tables
  that express the same invariants through supported relationships. Review that
  schema change with Richshard rather than silently weakening the logical rules.

Service-level authorization, publication checks, and all-child completeness checks
are still needed regardless of which physical strategy is chosen. Do not use
GenericForeignKey as a shortcut for these integrity-critical resource targets.

## Suggested team review order

1. Accept the content-version uniqueness correction and the corrected R12/R13
   cardinalities; add the missing authorship and audit connectors.
2. Confirm typed-content and same-target enforcement strategy with Richshard.
3. Agree on publication/review, score/level rules, and deletion behavior before
   those respective sections are migrated.
4. Implement SKILL/STUDENT_SKILL next, preserving the tested account section.
   Add course selection when CONTENT_ITEM's course identity is available.
5. Introduce reference publication, then comparison snapshots/outcomes and learning
   recommendations as individually tested milestones.

## References

- [Supplied full-attribute ERD](<Compass ERD Final Draft.png>)
- [Implemented account mapping](erd-django-mapping.md)
- [Django composite-key limitations](https://docs.djangoproject.com/en/6.1/topics/composite-primary-key/)
- [Django model constraints](https://docs.djangoproject.com/en/6.1/ref/models/constraints/)
- [Django field/deletion semantics](https://docs.djangoproject.com/en/6.1/ref/models/fields/)
