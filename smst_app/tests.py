from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(ROOT_URLCONF="smst_ai.urls")
class LandingPageTests(TestCase):
    """The three public app landing pages and their way in from the catalogue."""

    def setUp(self):
        self.client = self.client_class(
            SERVER_NAME="app.smst.africa",
            HTTP_HOST="app.smst.africa",
        )

    def test_each_landing_page_opens(self):
        expected = {
            "works": ("SmSt Works", "The floor,", "https://app.smst.africa/smst_works/"),
            "stocks": ("SmSt Stocks", "The shelf,", "https://app.smst.africa/smst_stocks/"),
            "finances": (
                "SmSt Finances",
                "Every shilling,",
                "https://app.smst.africa/smst_finances/",
            ),
        }
        for slug, (name, headline, app_url) in expected.items():
            with self.subTest(slug=slug):
                response = self.client.get(reverse(f"{slug}"))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertIn(name, html)
                self.assertIn(headline, html)
                self.assertIn(app_url, html)
                self.assertIn(f"/static/smst_app/css/{slug}.css", html)
                self.assertIn("/static/smst_app/js/landing.js", html)
                self.assertNotIn("\u2014", html)

    def test_catalogue_links_to_every_landing_page(self):
        response = self.client.get(reverse("apps") + "/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for slug in ("works", "stocks", "finances"):
            self.assertIn(reverse(f"{slug}"), html)
