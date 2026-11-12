"""Rank live dashboard jobs in SQL before loading editions and requirements."""
from decimal import Decimal

from django.db.models import Case, DecimalField, F, IntegerField, Q, Subquery, Sum, Value, When
from django.db.models.functions import Least, Round

from reference.models import ContentRequirement, ContentVersion
from reference.selectors import latest_available


def top_job_versions(levels, limit):
    reported = {skill_id: level for skill_id, level in levels.items() if level is not None}
    if not reported or limit <= 0:
        return []

    # Choose the latest available edition before testing relevance. A newer
    # unrelated edition must not expose an older, better-matching edition.
    latest = latest_available("job").values("pk")
    relevant = ContentRequirement.objects.filter(
        Q(weight__gt=0) | Q(mandatory=True),
        skill_id__in=reported, required_level__gt=0,
    ).values("version_id")
    requirements = ContentRequirement.objects.filter(
        version_id__in=Subquery(latest),
    ).filter(version_id__in=Subquery(relevant))

    # Mirror weighted_skill_match_v1's exact weighted units (60 is divisible
    # by every positive required level), including zero and unknown inputs.
    level = Case(*(When(skill_id=sid, then=Value(value)) for sid, value in reported.items()),
                 default=Value(0), output_field=IntegerField())
    factor = Case(*(When(required_level=n, then=Value(60 // n)) for n in range(1, 6)),
                  default=Value(0), output_field=IntegerField())
    numeric = DecimalField(max_digits=40, decimal_places=12)
    scored = Q(required_level__gt=0, weight__gt=0)
    ranked = (requirements.order_by().values("version_id", "version__item_id")
              .annotate(total_weight=Sum("weight", filter=scored),
                        credit_units=Sum(F("weight") * Least(level, F("required_level")) * factor,
                                         filter=scored, output_field=numeric))
              .filter(total_weight__gt=0)
              .annotate(score=Round(Value(Decimal(100)) * F("credit_units") /
                                    (Value(Decimal(60)) * F("total_weight")), precision=2))
              .order_by("-score", "version__item_id")
              .values_list("version_id", flat=True)[:limit])
    ids = list(ranked)
    if not ids:
        return []
    versions = {version.pk: version for version in ContentVersion.objects.filter(pk__in=ids)
                .select_related("details__company").prefetch_related("requirements")}
    return [versions[pk] for pk in ids]
