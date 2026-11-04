"""Authenticated, owner-scoped comparison pages."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .forms import ComparisonForm
from .services import list_matches


@login_required(login_url="accounts:login")
@require_GET
def comparison_list(request):
    matches = list_matches(actor=request.user)
    form = ComparisonForm()

    return render(
        request,
        "comparisons/comparison_list.html",
        {
            "form": form,
            "matches": matches,
            "has_targets": (
                form.fields["target_version"].queryset.exists()
            ),
        },
    )