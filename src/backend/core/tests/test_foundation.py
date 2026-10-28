from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import resolve, reverse


class FoundationTests(SimpleTestCase):
    """Foundation checks intentionally forbid database queries."""

    def test_home_uses_app_template_and_shared_layout(self):
        # Confirm the app page composes the shared shell, not a standalone draft.
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        for template in ["core/home.html", "base.html", "includes/header.html", "includes/footer.html"]:
            self.assertTemplateUsed(response, template)
        self.assertContains(response, "Chart your path from classroom to career.")
        self.assertContains(response, 'id="main-content"')

    def test_route_belongs_to_core_app(self):
        self.assertEqual(resolve("/").view_name, "core:home")

    def test_template_assets_are_discoverable(self):
        # Check both retained draft assets and app-owned assets through finders.
        # This verifies Django discovery, not visual layout in a browser.
        response = self.client.get(reverse("core:home"))
        for asset in ["draft/css/style.css", "core/css/layout.css"]:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))
                self.assertContains(response, f'/static/{asset}')

    def test_account_and_admin_features_are_not_exposed_yet(self):
        # Update this expectation when real account/database integration lands.
        for path in ["/accounts/login/", "/admin/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
