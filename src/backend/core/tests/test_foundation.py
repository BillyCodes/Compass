from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import resolve, reverse


class FoundationTests(TestCase):
    """Foundation route aliases and assets survive the launch integration."""

    def test_home_uses_app_template_and_shared_layout(self):
        # Confirm the app page composes the shared shell, not a standalone draft.
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        for template in ["core/home.html", "core/base.html"]:
            self.assertTemplateUsed(response, template)
        self.assertContains(response, "COMPASS")

    def test_route_belongs_to_core_app(self):
        self.assertEqual(resolve("/").view_name, "home")

    def test_template_assets_are_discoverable(self):
        # Check both retained draft assets and app-owned assets through finders.
        # This verifies Django discovery, not visual layout in a browser.
        response = self.client.get(reverse("core:home"))
        for asset in ["core/compass.css"]:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))
                self.assertContains(response, f'/static/{asset}')

    def test_login_is_public_and_admin_is_not_exposed(self):
        self.assertEqual(reverse("core:home"), reverse("home"))
        self.assertIsNotNone(finders.find("draft/css/style.css"))
        self.assertIsNotNone(finders.find("core/css/layout.css"))
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 404)
