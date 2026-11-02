"""Pure, versioned calculation; no HTTP or database side effects."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.core.exceptions import ValidationError

ALGORITHM = "weighted_skill_match_v1"


@dataclass(frozen=True)
class Requirement:
    skill_id: object
    required_level: int
    weight: Decimal
    mandatory: bool


@dataclass(frozen=True)
class Outcome:
    skill_id: object
    status: str
    gap: int | None


@dataclass(frozen=True)
class Calculation:
    score: Decimal
    mandatory_status: str
    reported_count: int
    relevant_count: int
    is_provisional: bool
    outcomes: tuple[Outcome, ...]


def calculate(requirements, levels):
    """Missing dictionary keys/None mean unknown; zero is explicit proficiency."""
    requirements = tuple(requirements)
    if len({r.skill_id for r in requirements}) != len(requirements):
        raise ValidationError("A skill may appear only once in a comparison target.")
    for r in requirements:
        if type(r.required_level) is not int or not 0 <= r.required_level <= 5:
            raise ValidationError("Required levels must be integers from 0 to 5.")
        if not isinstance(r.weight, Decimal) or not r.weight.is_finite() or not 0 <= r.weight <= Decimal("999999.9999"):
            raise ValidationError("Weights must be finite nonnegative decimals within the schema limit.")
        if type(r.mandatory) is not bool:
            raise ValidationError("Mandatory must be a boolean.")
        level = levels.get(r.skill_id)
        if level is not None and (type(level) is not int or not 0 <= level <= 5):
            raise ValidationError("Reported proficiency must be an integer from 0 to 5.")
    scored = [r for r in requirements if r.required_level > 0 and r.weight > 0]
    if not scored:
        raise ValidationError("The target needs a positive-level, positive-weight requirement.")
    relevant = [r for r in requirements if r.required_level > 0 and (r.weight > 0 or r.mandatory)]
    reported = sum(levels.get(r.skill_id) is not None for r in relevant)
    if reported == 0:
        raise ValidationError("Report at least one relevant proficiency before saving a comparison.")
    with localcontext() as context:
        context.prec = 40
        # 60 is divisible by every positive level (1–5). Accumulate exact
        # weighted units before the final division, avoiding repeating ratios.
        credit_units = sum((r.weight * min(levels.get(r.skill_id) or 0, r.required_level) * (60 // r.required_level) for r in scored), Decimal(0))
        score = (100 * credit_units / (60 * sum(r.weight for r in scored))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    outcomes = []
    for r in requirements:
        level = levels.get(r.skill_id)
        if r.required_level == 0:
            outcomes.append(Outcome(r.skill_id, "met", 0))
        elif level is None:
            outcomes.append(Outcome(r.skill_id, "unreported", None))
        else:
            gap = max(r.required_level - level, 0)
            outcomes.append(Outcome(r.skill_id, "gap" if gap else "met", gap))
    mandatory = [o for r, o in zip(requirements, outcomes) if r.mandatory]
    status = ("not_applicable" if not mandatory else "not_met" if any(o.status == "gap" for o in mandatory)
              else "undetermined" if any(o.status == "unreported" for o in mandatory) else "met")
    return Calculation(score, status, reported, len(relevant), reported < len(relevant), tuple(outcomes))
