"""Read published editions through the established availability policy."""
from .services import available_content_versions


def latest_available(kind):
    versions = available_content_versions(kind=kind)
    if kind in ("career", "job"):
        versions = versions.exclude(requirements__skill__status="retired")
    return (versions.select_related("details__company")
            .order_by("item_id", "-version_no").distinct("item_id"))
