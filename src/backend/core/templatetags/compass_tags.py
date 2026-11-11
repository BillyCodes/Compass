import math

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from skills.models import ProficiencyLevel
from pilot.services.skillprint import CATEGORY_LABELS, category_key

register = template.Library()


@register.simple_tag(takes_context=True)
def pagination_url(context, parameter, number):
    query = context["request"].GET.copy()
    query[parameter] = number
    return "?" + query.urlencode()

# Presentation labels follow the established backend scale; no pilot models.
LEVEL_LABELS = dict(ProficiencyLevel.choices)
CAT_TINT = {"programming": "t-blue", "data": "t-violet", "systems": "t-green", "security": "t-red", "cloud": "t-amber", "professional": "t-violet"}


@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.filter
def level_label(level):
    return LEVEL_LABELS.get(level, "")


@register.filter
def level_pct(level):
    return int(level or 0) * 20


@register.filter
def cat_tint(cat):
    return CAT_TINT.get(category_key(cat), "t-blue")


@register.filter
def cat_key(cat):
    """Stable CSS/chart key for a free-text skill category."""
    return category_key(cat) or "other"


@register.filter
def cat_label(cat):
    return CATEGORY_LABELS.get(category_key(cat), cat or "Other")


@register.filter
def first_word(text):
    return str(text or "").split(" ")[0]


@register.filter
def initials(text):
    parts = [p for p in str(text or "").replace("(", " ").split() if p[:1].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or "C"


@register.filter
def av(value):
    return f"av-{sum(map(ord, str(value))) % 6}"


@register.filter
def status_class(status):
    return {"Strong Match": "strong", "Developing Match": "developing"}.get(status, "early")


@register.simple_tag
def dots(level):
    level = int(level or 0)
    return format_html(
        '<span class="dots" aria-label="{} of 5">{}</span>',
        level,
        mark_safe("".join(f'<i class="{"on" if i < level else ""}"></i>' for i in range(5))),
    )


@register.simple_tag
def ring(value, size="", label="Match"):
    """Progress ring 0–100. Color: green ≥75, amber ≥45, blue below."""
    v = max(0.0, min(100.0, float(value or 0)))
    r = 52
    c = 2 * math.pi * r
    cls = "" if v >= 75 else ("mid" if v >= 45 else "low")
    return format_html(
        '<div class="ring {}"><svg viewBox="0 0 132 132" aria-hidden="true">'
        '<circle class="track" cx="66" cy="66" r="{}"/>'
        '<circle class="bar {}" cx="66" cy="66" r="{}" stroke-dasharray="{} {}"/></svg>'
        '<div class="val"><div>{}%<small>{}</small></div></div></div>',
        size, r, cls, r, f"{c * v / 100:.1f}", f"{c:.1f}", int(round(v)), label,
    )
