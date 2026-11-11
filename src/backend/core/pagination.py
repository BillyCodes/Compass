"""Shared page size and forgiving page-number handling for student lists."""
from django.core.paginator import Paginator

PAGE_SIZE = 20


def paginate(request, queryset, parameter="page"):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get(parameter))
