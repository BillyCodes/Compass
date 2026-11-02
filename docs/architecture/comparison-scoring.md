# Agreed comparison scoring rules

Agreed November 1, 2026. This document specifies the first comparison algorithm;
the [comparison batch](comparison-batch.md) now implements these models, services,
and migrations.
Use `weighted_skill_match_v1` as the algorithm identifier when implementing it.

## Weighted skill alignment

Use the existing 0–5 proficiency scale. For each requirement with required level
greater than zero and weight greater than zero:

```text
skill_match = min(reported_level / required_level, 1)
overall_score = 100 * sum(weight * skill_match) / sum(weight)
```

An unreported level earns zero credit but remains unknown in stored data.
Keep its weight in the denominator. Exceeding one requirement earns no extra
credit beyond 100% for that skill. Default weight is 1; weight 2 has twice the
influence of weight 1. Weight zero excludes a requirement from the percentage,
but does not disable a mandatory requirement.

A required level of zero means no proficiency is required. Exclude it from
both numerator and denominator; it is automatically satisfied even if the student
has not reported that skill. Never divide by zero. A comparable target must have
at least one requirement with both positive required level and positive weight.
The implementation enforces this for new publications and validates targets
again at comparison time; existing published editions are not rewritten.

Calculate with decimal arithmetic without rounding individual contributions;
round the final percentage to two decimal places using ROUND_HALF_UP. The
percentage describes alignment with recorded requirements, not employment
probability. Proportional credit across the ordinal scale is an agreed product
rule, not a claim that expertise can be measured precisely by these ratios.

Example: Python requires 4, student reports 3, weight 2; SQL requires 3, student
reports 3, weight 1; communication requires 2, student reports 1, weight 1.
The score is `100 * (2 * 0.75 + 1 * 1 + 1 * 0.5) / 4 = 75%`.

## Mandatory requirements

Evaluate all mandatory requirements independently from the score, including
zero-weight requirements. Apply these statuses in this order:

1. `not_applicable`: no mandatory requirements exist.
2. `not_met`: at least one reported mandatory skill is below its required level.
3. `undetermined`: no known mandatory gap exists, but at least one mandatory
   requirement with positive required level has an unreported input.
4. `met`: every mandatory requirement is satisfied.

A known mandatory gap takes precedence over an unknown input. Preserve both in
per-skill outcomes so the explanation can identify each. Do not reduce or zero
the calculated percentage because of mandatory status, and do not block career
exploration or learning recommendations. Present score and mandatory status
together; neither is an employment eligibility decision.

## Missing inputs and completeness

Explicit level 0 means the student reports no proficiency. An absent input means
unreported; preserve it as unknown, never silently store it as explicit level 0.

For completeness, relevant requirements have positive required level and either
positive weight or mandatory status. Report the number with explicit inputs over
the number of relevant requirements, for example, `4 of 6 relevant skills
reported`. An explicit zero counts as reported. Zero-weight optional requirements
do not affect score, mandatory status, or completeness.

Label a result provisional whenever any relevant input is unreported. If every
relevant input is unreported, prompt the student to complete their profile and
do not save a comparison. Otherwise a partial comparison may be saved with its
conservative score, completeness, unknown inputs, and mandatory status.

For example, two equally weighted requirements at level 3 with one reported at
level 3 and the other unreported yield a provisional 50% score and `1 of 2`
completeness. Reporting the missing skill at level 0 keeps the score at 50% but
makes the input set complete and records a known skill gap.

Known skill gaps can drive learning recommendations. Unknown skills should first
prompt proficiency input. Course selection alone never changes proficiency.
The [comparison batch](comparison-batch.md) records the subsequently confirmed
mandatory-gap-first recommendation rule and its deterministic tie breakers.

## Persistence and verification for the next batch

The server must calculate results from the student's owned inputs and an
eligible published career/job version. Save the result, exact input snapshots,
and one outcome per applicable requirement atomically. Preserve unknown inputs
explicitly, the target version, and the algorithm identifier so later profile
edits do not change historical results. Clients must not supply trusted scores.

Verify partial credit, capped credit, unequal and zero weights, zero required
levels, missing versus explicit-zero inputs, all-missing rejection, mandatory
status precedence, completeness, decimal rounding, and snapshot stability.
The agreement itself did not change the database; the subsequent comparison
batch adds new tables without recalculating existing data.
