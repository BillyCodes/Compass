# Comparison database batch

Implemented November 1, 2026, using the [agreed scoring rules](comparison-scoring.md).
The `comparisons` Django app owns calculations and private results. This batch
adds backend services and four tables; no new routes, forms, or demo records.
Audit events remain a later batch.

## ERD-to-Django mapping

| ERD table | Django model | Purpose and physical mapping |
| --- | --- | --- |
| MATCH_RESULT | `comparisons.MatchResult` | UUID `match_id`; student FK; exact target edition and kind; algorithm, score, mandatory status, completeness, provisional flag, timestamp |
| MATCH_INPUT_SKILL | `comparisons.MatchInputSkill` | UUID `input_id`; unique `(match_id, skill_id)`; nullable `level_used` preserves unreported inputs |
| MATCH_SKILL_RESULT | `comparisons.MatchSkillResult` | UUID `outcome_id`; unique `(match_id, skill_id)`; exact target edition, status, and nullable gap |
| RECOMMENDATION | `comparisons.Recommendation` | UUID `recommendation_id`; exact learning edition and kind; unique edition and positive rank per match; frozen JSON explanation |

The physical PostgreSQL table names are lowercase versions of the ERD names.
UUID child keys support Django; logical pairs remain unique. `finalized` and
`recommendation_count` are internal integrity fields on MATCH_RESULT, not student
input fields. A comparison is assembled and sealed within one transaction; an
unfinished comparison cannot commit.

Five extra PostgreSQL composite foreign keys enforce:

- The comparison target is the stated career/job kind.
- A recommendation is the stated course/resource kind.
- Each outcome belongs to the same target edition as its result.
- Each outcome references an actual requirement of that exact edition and skill.
- Each outcome has a corresponding saved input for that match and skill.

The input/outcome FK is initially deferred because Django's deletion collector
may remove inputs before outcomes. Whole-result or student deletion works;
individual removal of required snapshots cannot commit.

## Calculation and snapshots

The server reads proficiency from the actor's student profile, never from a
caller-supplied student ID or score. Compare only a published career/job edition
whose item is available, job is unexpired, and requirement skills are active.
Publication now requires at least one requirement with both positive level and
positive weight; comparisons recheck this condition for older editions too.
Existing reference data is not rewritten by that tightened publication rule.

The service locks the target item, target edition, and requirement skills in a
stable order. Proficiency services use the same skill locks, including for a
previously unreported skill. A single query captures relevant student inputs.
One input and outcome is stored for every target requirement, including
zero-weight and zero-level requirements. Evidence text and unrelated profile
skills are not copied into a comparison.

`weighted_skill_match_v1` implements weighted, capped partial credit, mandatory
status precedence, unknown versus explicit-zero inputs, completeness, all-missing
rejection, and final half-up rounding to two decimal places. Both Python and SQL
accumulate exact weighted units using 60 (divisible by levels 1–5), then divide
once. This avoids rounding intermediate repeating fractions.

No new score calculation is performed when reading history. Inputs remain fixed
when a student edits proficiency, and referenced requirements/learning mappings
remain protected by the existing published-history guards. A later retirement
blocks new uses but does not erase private history.

## Recommendations

The user confirmed prioritizing known mandatory skill gaps before other known
gaps. The first deterministic rule is
`mandatory_gaps_then_weighted_coverage_v1`:

1. Consider the latest currently available published course/resource edition for
   each content item. Ignore retired items, unavailable editions, and editions
   referencing retired skills.
2. For each known relevant gap, compute useful coverage as
   `max(0, min(coverage_level, required_level) - level_used)`.
3. Keep candidates with positive useful coverage. Rank by the number of mandatory
   gaps covered, descending; then sum of `requirement weight * useful coverage`,
   descending; then version UUID, ascending, to break ties reproducibly.
4. Save all matching candidates with consecutive ranks and a JSON explanation
   containing the rule ID, skill UUIDs, mandatory flags, and covered gap levels.

Unknown inputs do not generate learning recommendations; they prompt proficiency
input first. Zero-weight optional gaps do not generate recommendations. A
zero-weight mandatory gap still takes priority. The rule supplies useful coverage
suggestions, not verified proficiency gains or a guarantee of course completion.
Selected courses never automatically increase skill levels.

No recommendation limit or pagination is added in this backend milestone. A
later interface may paginate saved ranks. Recommendation availability is checked
when selecting and inserting its snapshot; later withdrawal is permitted and
retains that historical recommendation. Interfaces should check current
availability before presenting an actionable learning link. If a candidate is
withdrawn while assembling a result, database checks may reject the transaction;
the caller can retry the comparison.

## Services and privacy

```python
from comparisons.services import (
    create_comparison, delete_match, get_match, list_matches,
)

result = create_comparison(actor=request.user, target_version_id=version_id)
results = list_matches(actor=request.user)
saved = get_match(actor=request.user, match_id=result.pk)
delete_match(actor=request.user, match_id=result.pk)
```

These require an active student role and profile. Reads and deletion are scoped
to the actor's student; maintainers receive no blanket access to private results.
A foreign match UUID produces `MatchResult.DoesNotExist`. Views added later must
use these services, including owner-scoped lookup before traversing child rows.

Whole-result deletion cascades to its private inputs, outcomes, and
recommendations. Student deletion removes that student's results. Compared and
recommended editions, requirements, and skills are protected reference history.

## PostgreSQL integrity and migrations

`reference.0007_comparable_requirements` wraps the existing publication validator
with the positive-level/positive-weight rule and can reverse it independently.
`comparisons.0001_initial` creates the models. `comparisons.0002_integrity_guards`
adds composite FKs, snapshot guards, and deferred completeness checks.

Ordinary row writes cannot edit a saved result, edit its children, append children
after finalization, save partial children, or commit a score/mandatory status/
completeness inconsistent with its saved inputs. The service validates immediately
before returning; deferred triggers also check integrity at transaction end.
Delete an entire private result rather than individual snapshot rows.

These are integrity checks, not database-level authorization or an external audit
log. Trusted code must still enforce ownership; database administrators retain
control over DDL and trigger settings. New algorithm identifiers require retained
implementation code and a migration updating the known-algorithm constraint and
validator without changing old result semantics.

## Verification

Run from the repository root with local PostgreSQL available:

```sh
.venv/bin/python src/backend/manage.py test core accounts skills reference comparisons
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
```

The 41 new comparison tests cover scoring edge cases, authorization, exact
snapshots, withdrawal/expiry, recommendation priority and history, rollback,
forged SQL scores, cross-target/type integrity, real commits, concurrent
proficiency writes, and migration reversal/reinstallation. The complete suite
contains 177 tests. Tests use an isolated database, not the Compass application
data. The local migration verifies existing record counts and creates empty
comparison tables without seeding or publishing content.

## Remaining work

The planned ERD now has 20 of 21 application tables. AUDIT_EVENT and D1–D3 remain.
Frontend comparison/proficiency/review screens, representative seed content, and
complete browser workflows remain separate work after database services.
