from django.test import TestCase, override_settings
from django.urls import reverse

from . import content


@override_settings(ROOT_URLCONF="smst_ai.urls")
class SupportCentreTests(TestCase):
    """The public support hub and the per-app support pages."""

    def test_hub_opens_and_lists_every_app(self):
        response = self.client.get(reverse("smst_support:hub"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn("SmSt Support", html)
        self.assertIn(content.HUB["title"], html)
        self.assertIn(content.HUB["lede"], html)
        for slug, name in (
            ("works", "SmSt Works"),
            ("stocks", "SmSt Stocks"),
            ("finances", "SmSt Finances"),
        ):
            with self.subTest(slug=slug):
                self.assertIn(name, html)
                self.assertIn(reverse("smst_support:app", kwargs={"slug": slug}), html)

        self.assertIn("Manuals", html)
        self.assertIn("Tips and tricks", html)
        self.assertIn("Version updates", html)

    def test_each_app_support_page_opens(self):
        expected = {
            "works": ("Run the floor without the guesswork.", "The live job timeline"),
            "stocks": ("Catalogue the shelf, then let the numbers catch up.", "The reorder list"),
            "finances": (
                "Keep the book balanced, then read it without a second tally.",
                "The weekly spend chart",
            ),
        }
        for slug, (headline, latest) in expected.items():
            with self.subTest(slug=slug):
                response = self.client.get(
                    reverse("smst_support:app", kwargs={"slug": slug})
                )
                self.assertEqual(response.status_code, 200)

                html = response.content.decode()
                self.assertIn(headline, html)
                self.assertIn(latest, html)
                self.assertIn(f"lp--{slug}", html)
                self.assertIn(f"/static/smst_app/css/{slug}.css", html)
                self.assertIn("/static/smst_support/css/support.css", html)
                self.assertIn("Manuals", html)
                self.assertIn("Tips and tricks", html)
                self.assertIn("Version updates", html)
                self.assertNotIn("\u2014", html)

    def test_each_app_support_page_carries_its_manual(self):
        for slug in ("works", "stocks", "finances"):
            with self.subTest(slug=slug):
                support = content.support_app(slug)
                html = self.client.get(
                    reverse("smst_support:app", kwargs={"slug": slug})
                ).content.decode()
                first = support["manuals"][0]
                self.assertIn(first["title"], html)
                self.assertIn(first["steps"][0], html)
                self.assertIn(support["tips"][0]["title"], html)

    def test_unknown_app_is_not_found(self):
        response = self.client.get("/support/unknown/")
        self.assertEqual(response.status_code, 404)

    def test_marketing_header_links_to_support(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(reverse("smst_support:hub"), response.content.decode())

    def test_landing_pages_link_to_support(self):
        for slug in ("works", "stocks", "finances"):
            with self.subTest(slug=slug):
                html = self.client.get(reverse(slug)).content.decode()
                self.assertIn(reverse("smst_support:hub"), html)
