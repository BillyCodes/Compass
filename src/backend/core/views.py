from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Render the replaceable home template without querying student data."""

    template_name = "core/home.html"
