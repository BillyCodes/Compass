"""Read published editions through the established availability policy."""
from django.db.models import Subquery

from .services import available_content_versions


def available_learning_versions(kind=None):
    """Published learning editions whose mapped skills are still active."""
    return (available_content_versions(kind=kind).filter(kind__in=["course", "resource"])
            .exclude(skill_mappings__skill__status="retired"))


def latest_available_learning(kind=None):
    # Apply skill eligibility AFTER choosing the latest available edition.
    # Withdrawal permits an older published edition; an unsuitable newer
    # published edition must not silently expose an older one instead.
    latest = (available_content_versions(kind=kind).filter(kind__in=["course", "resource"])
              .order_by("item_id", "-version_no").distinct("item_id").values("pk"))
    return available_learning_versions(kind).filter(pk__in=Subquery(latest)).select_related("details__company")


def latest_available(kind):
    if kind in ("course", "resource"):
        return latest_available_learning(kind).order_by("item_id")
    versions = available_content_versions(kind=kind)
    if kind in ("career", "job"):
        versions = versions.exclude(requirements__skill__status="retired")
    return (versions.select_related("details__company")
            .order_by("item_id", "-version_no").distinct("item_id"))
