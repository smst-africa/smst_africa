"""Tests for SmSt Stocks."""

from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
    get_user_model,
)
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase, override_settings
from django.urls import reverse

from smst_finances.models import FinanceEntry, FinanceOption, Receipt
from smst_finances.services import ensure_default_accounts

from . import finance_bridge
from .models import CartLine, Order, Product, ReportRun, Shop, StockMovement
from .reports.builder import build_report
from .services import (
    StockError,
    add_to_cart,
    apply_kind_sign,
    cancel_order,
    cart_totals,
    check_item_limit,
    create_order,
    plan_limits,
    process_cart,
    process_cart_line,
    record_delivery,
    record_movement,
    release_cart_line,
    shop_summary,
)

User = get_user_model()


@override_settings(ROOT_URLCONF="smst_app.urls")
class StockTestCase(TestCase):
    """A shop with two items, and the owner of it."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="njeri", email="njeri@example.test", password="s3cret-pass-123"
        )
        # the app lives on the app host, so the tests are run as that host
        self.client = self.client_class(
            SERVER_NAME="app.smst.africa", HTTP_HOST="app.smst.africa"
        )
        self._sign_in(self.user)
        self.shop = Shop.objects.create(owner=self.user, name="Sokoni Traders")
        self.sugar = Product.objects.create(
            shop=self.shop,
            name="Mumias Sugar 1kg",
            buying_price=Decimal("149"),
            selling_price=Decimal("168"),
            quantity=Decimal("24"),
            reorder_level=Decimal("6"),
            unit="piece",
        )
        self.oil = Product.objects.create(
            shop=self.shop,
            name="Kijani Cooking Oil 1L",
            buying_price=Decimal("331"),
            selling_price=Decimal("385"),
            quantity=Decimal("8"),
            reorder_level=Decimal("10"),
            unit="litre",
        )

    def _sign_in(self, user):
        """Sign the user in without going through the login form.

        The session is written directly, which keeps the tests away from the
        login backends and their rate limiting.
        """
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = (
            "allauth.account.auth_backends.AuthenticationBackend"
        )
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    # ------------------------------------------------------------- models
    def test_stock_state(self):
        self.assertEqual(self.sugar.stock_state, "in_stock")
        self.assertEqual(self.oil.stock_state, "low")

        self.oil.quantity = Decimal("0")
        self.assertEqual(self.oil.stock_state, "out")

    def test_margin(self):
        self.assertAlmostEqual(float(self.sugar.margin), 11.31, places=2)
        self.assertEqual(self.sugar.margin_value, Decimal("19"))

    def test_suggested_order(self):
        # reorder level 10, 8 in hand, so ask for 12 to double the level
        self.assertEqual(self.oil.suggested_order, Decimal("12"))
        self.assertEqual(self.oil.order_cost, Decimal("3972"))

    def test_slugs_are_made(self):
        self.assertEqual(self.sugar.slug, "mumias-sugar-1kg")
        other = Product.objects.create(
            shop=self.shop, name="Mumias Sugar 1kg", selling_price=Decimal("170")
        )
        self.assertEqual(other.slug, "mumias-sugar-1kg-2")

    # ----------------------------------------------------------- services
    def test_plan_limits(self):
        free = plan_limits(self.user)
        self.assertEqual(free["plan"], "free")
        self.assertEqual(free["shops"], 1)
        self.assertEqual(free["items_per_shop"], 50)

    def test_item_limit_is_enforced(self):
        Product.objects.filter(shop=self.shop).delete()
        for index in range(50):
            Product.objects.create(
                shop=self.shop, name=f"Item {index}", selling_price=Decimal("10")
            )
        with self.assertRaises(StockError):
            check_item_limit(self.shop)

    def test_apply_kind_sign(self):
        self.assertEqual(apply_kind_sign(StockMovement.SALE, 3), Decimal("-3"))
        self.assertEqual(apply_kind_sign(StockMovement.DELIVERY, 20), Decimal("20"))
        self.assertEqual(apply_kind_sign(StockMovement.ADJUSTMENT, -4), Decimal("-4"))

    @patch("smst_stocks.services.broadcast_product")
    def test_recording_a_sale(self, broadcast):
        movement = record_movement(self.sugar, StockMovement.SALE, 3, user=self.user)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("21"))
        self.assertEqual(movement.quantity, Decimal("-3"))
        self.assertTrue(broadcast.called)

    @patch("smst_stocks.services.broadcast_product")
    def test_a_sale_beyond_the_stock_is_refused(self, broadcast):
        with self.assertRaises(StockError):
            record_movement(self.sugar, StockMovement.SALE, 500, user=self.user)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("24"))

    @patch("smst_stocks.services.broadcast_product")
    def test_recording_a_delivery_of_several_lines(self, broadcast):
        record_delivery(
            self.shop,
            [
                {"product": self.sugar.id, "quantity": 10},
                {"product": self.oil.id, "quantity": 12},
            ],
            note="From Nzozi Ltd",
            user=self.user,
        )
        self.sugar.refresh_from_db()
        self.oil.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("34"))
        self.assertEqual(self.oil.quantity, Decimal("20"))

    @patch("smst_stocks.services.broadcast_product")
    @patch("smst_stocks.services.broadcast_shop")
    def test_an_order_holds_the_stock(self, shop_broadcast, product_broadcast):
        order = create_order(self.sugar, 2, "Amina Otieno", "+254 700 111 222")
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("22"))
        self.assertEqual(order.status, Order.PENDING)
        self.assertTrue(order.reference.startswith("SS-"))
        self.assertEqual(order.total, Decimal("336"))

    @patch("smst_stocks.services.broadcast_product")
    @patch("smst_stocks.services.broadcast_shop")
    def test_an_order_beyond_the_stock_is_refused(self, shop_broadcast, product_broadcast):
        with self.assertRaises(StockError):
            create_order(self.sugar, 99, "Amina Otieno", "+254 700 111 222")
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("24"))

    @patch("smst_stocks.services.broadcast_product")
    @patch("smst_stocks.services.broadcast_shop")
    def test_cancelling_an_order_puts_the_stock_back(self, shop_broadcast, product_broadcast):
        order = create_order(self.sugar, 5, "Amina Otieno", "+254 700 111 222")
        cancel_order(order)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("24"))
        self.assertEqual(order.status, Order.CANCELLED)

    def test_shop_summary(self):
        summary = shop_summary(self.shop)
        self.assertEqual(summary["products"], 2)
        self.assertEqual(summary["units"], Decimal("32"))
        self.assertEqual(summary["stock_value"], Decimal("7112"))
        self.assertEqual(summary["low_stock_count"], 1)

    # --------------------------------------------------- stock to finances
    @patch("smst_stocks.services.broadcast_product")
    def test_a_sale_posts_money_in_to_finances(self, broadcast):
        roles = ensure_default_accounts(self.shop)
        movement = record_movement(
            self.sugar,
            StockMovement.SALE,
            3,
            user=self.user,
            account=roles["cash"],
        )
        entry = FinanceEntry.objects.get(movement=movement)
        self.assertEqual(entry.kind, FinanceEntry.INCOME)
        self.assertEqual(entry.amount, Decimal("504.00"))
        self.assertEqual(entry.account, roles["sales"])
        self.assertEqual(entry.payment_account, roles["cash"])
        self.assertEqual(roles["cash"].balance, Decimal("504.00"))

    @patch("smst_stocks.services.broadcast_product")
    def test_a_delivery_posts_money_out_of_finances(self, broadcast):
        roles = ensure_default_accounts(self.shop)
        movement = record_movement(
            self.sugar,
            StockMovement.DELIVERY,
            10,
            user=self.user,
            account=roles["cash"],
        )
        entry = FinanceEntry.objects.get(movement=movement)
        self.assertEqual(entry.kind, FinanceEntry.EXPENSE)
        self.assertEqual(entry.amount, Decimal("1490.00"))
        self.assertEqual(entry.account, roles["inventory"])
        self.assertEqual(roles["cash"].balance, Decimal("-1490.00"))

    @patch("smst_stocks.services.broadcast_product")
    def test_a_movement_without_an_account_stays_in_stock(self, broadcast):
        record_movement(self.sugar, StockMovement.SALE, 1, user=self.user)
        self.assertEqual(FinanceEntry.objects.count(), 0)

    @patch("smst_stocks.services.broadcast_product")
    def test_a_loss_is_always_posted(self, broadcast):
        movement = record_movement(
            self.sugar, StockMovement.LOSS, 2, user=self.user
        )
        entry = FinanceEntry.objects.get(movement=movement)
        self.assertEqual(entry.kind, FinanceEntry.LOSS)
        self.assertEqual(entry.amount, Decimal("298.00"))
        self.assertEqual(entry.payment_account.code, "1200")

    @patch("smst_stocks.services.broadcast_product")
    def test_the_movement_api_posts_to_finances(self, broadcast):
        roles = ensure_default_accounts(self.shop)
        response = self.client.post(
            reverse("smst_stocks:stock_product-movement", args=[self.sugar.id]),
            {
                "kind": "sale",
                "quantity": 2,
                "account": roles["cash"].id,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIsNotNone(payload["finance"])
        self.assertEqual(payload["finance"]["kind"], "income")
        self.assertEqual(payload["finance"]["payment_account"], "Cash")
        self.assertEqual(payload["finance"]["amount"], "336.00")

    def test_the_delivery_api_posts_money_out(self):
        roles = ensure_default_accounts(self.shop)
        response = self.client.post(
            reverse("smst_stocks:stock_product-delivery"),
            {
                "shop": self.shop.id,
                "account": roles["cash"].id,
                "lines": [{"product": self.sugar.id, "quantity": 5}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        finance = response.json()["finance"]
        self.assertEqual(len(finance), 1)
        self.assertEqual(finance[0]["kind"], "expense")
        self.assertEqual(finance[0]["amount"], "745.00")

    def test_the_movement_form_offers_the_chart_of_accounts(self):
        response = self.client.get(reverse("smst_stocks:movements"))
        body = response.content.decode()
        self.assertIn('name="account"', body)
        self.assertIn("Money account", body)
        self.assertIn("1000", body)

    # ----------------------------------------------------------------- api
    def test_the_pages_open(self):
        for name in [
            "smst_stocks:dashboard",
            "smst_stocks:products",
            "smst_stocks:product_create",
            "smst_stocks:movements",
            "smst_stocks:low_stock",
            "smst_stocks:orders",
            "smst_stocks:reports",
            "smst_stocks:shops",
            "smst_stocks:links",
        ]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_the_product_page_opens(self):
        response = self.client.get(
            reverse("smst_stocks:product_detail", args=[self.sugar.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_the_rail_can_be_collapsed(self):
        response = self.client.get(reverse("smst_stocks:dashboard"))
        body = response.content.decode()
        # the control that collapses the rail, and the names it keeps for the
        # screen reader and the tooltip
        self.assertIn('data-rail-toggle', body)
        self.assertIn('aria-expanded="true"', body)
        self.assertIn('data-label="Dashboard"', body)
        self.assertIn('aria-current="page"', body)

    def test_the_dashboard_shows_the_figures(self):
        response = self.client.get(reverse("smst_stocks:dashboard"))
        body = response.content.decode()
        self.assertIn('data-stat="stock_value"', body)
        self.assertIn('data-stat="low_stock_count"', body)
        self.assertIn("Ksh", body)

    def test_the_items_page_offers_a_movement_in_the_row(self):
        response = self.client.get(reverse("smst_stocks:products"))
        body = response.content.decode()
        self.assertIn('data-inline-movement="sale"', body)
        self.assertIn(f'data-product-row="{self.sugar.id}"', body)

    def test_the_public_page_shows_the_stock_and_the_form(self):
        self.sugar.is_published = True
        self.sugar.save()
        response = self.client.get(
            reverse("smst_stocks:public_product", args=[self.sugar.share_token])
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("data-stock-text", body)
        self.assertIn("data-order-form", body)
        self.assertIn("in stock", body)
        self.assertIn(f'data-product="{self.sugar.share_token}"', body)

    def test_the_public_page_says_when_an_item_has_run_out(self):
        self.sugar.is_published = True
        self.sugar.quantity = 0
        self.sugar.save()
        response = self.client.get(
            reverse("smst_stocks:public_product", args=[self.sugar.share_token])
        )
        body = response.content.decode()
        self.assertIn("Out of stock", body)
        self.assertNotIn("data-order-form", body)

    def test_another_shops_product_is_hidden(self):
        other = User.objects.create_user(
            username="amina", email="amina@example.test", password="s3cret-pass-123"
        )
        other_shop = Shop.objects.create(owner=other, name="Bluewave Agro")
        other_product = Product.objects.create(
            shop=other_shop, name="Secret Item", selling_price=Decimal("10")
        )
        response = self.client.get(
            reverse("smst_stocks:product_detail", args=[other_product.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_creating_a_product(self):
        response = self.client.post(
            reverse("smst_stocks:stock_product-list"),
            {
                "shop": self.shop.id,
                "name": "Blue Band 250g",
                "buying_price": "331",
                "selling_price": "385",
                "quantity": "8",
                "reorder_level": "10",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Product.objects.filter(name="Blue Band 250g").exists())

    def test_recording_a_movement_through_the_api(self):
        response = self.client.post(
            reverse("smst_stocks:stock_product-movement", args=[self.sugar.id]),
            {"kind": "sale", "quantity": 3},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("21"))

    def test_a_sale_beyond_the_stock_is_refused_by_the_api(self):
        response = self.client.post(
            reverse("smst_stocks:stock_product-movement", args=[self.sugar.id]),
            {"kind": "sale", "quantity": 5000},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("in hand", response.json()["detail"])

    def test_the_public_page_needs_a_published_product(self):
        response = self.client.get(
            reverse("smst_stocks:public_product", args=[self.sugar.share_token])
        )
        self.assertEqual(response.status_code, 404)

        self.sugar.is_published = True
        self.sugar.save()
        response = self.client.get(
            reverse("smst_stocks:public_product", args=[self.sugar.share_token])
        )
        self.assertEqual(response.status_code, 200)

    def _anonymous_client(self):
        return self.client_class(
            SERVER_NAME="app.smst.africa", HTTP_HOST="app.smst.africa"
        )

    def test_a_customer_can_ask_for_an_item(self):
        self.sugar.is_published = True
        self.sugar.save()

        response = self._anonymous_client().post(
            reverse("smst_stocks:public_order_api"),
            {
                "product": self.sugar.share_token,
                "customer_name": "Amina Otieno",
                "customer_phone": "+254 700 111 222",
                "quantity": 2,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("reference", response.json())
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("22"))

    def test_a_customer_who_asks_for_too_much_is_told_no(self):
        self.sugar.is_published = True
        self.sugar.save()

        response = self._anonymous_client().post(
            reverse("smst_stocks:public_order_api"),
            {
                "product": self.sugar.share_token,
                "customer_name": "Amina Otieno",
                "customer_phone": "+254 700 111 222",
                "quantity": 500,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    # ------------------------------------------------------------- reports
    def test_the_reports_build(self):
        for kind in [
            ReportRun.STOCK,
            ReportRun.MOVEMENTS,
            ReportRun.LOW_STOCK,
            ReportRun.ORDERS,
        ]:
            for report_format in [ReportRun.PDF, ReportRun.XLSX]:
                run = ReportRun.objects.create(
                    shop=self.shop, kind=kind, format=report_format, created_by=self.user
                )
                build_report(run)
                run.refresh_from_db()
                self.assertEqual(run.status, ReportRun.READY)
                self.assertTrue(run.content)
                self.assertGreater(len(run.content), 500)
                self.assertTrue(run.filename.endswith(".pdf" if report_format == "pdf" else ".xlsx"))

    def test_the_pdf_is_a_pdf(self):
        run = ReportRun.objects.create(
            shop=self.shop, kind=ReportRun.STOCK, format=ReportRun.PDF
        )
        build_report(run)
        run.refresh_from_db()
        self.assertTrue(run.data.startswith(b"%PDF-"))

    def test_the_workbook_is_a_zip(self):
        run = ReportRun.objects.create(
            shop=self.shop, kind=ReportRun.STOCK, format=ReportRun.XLSX
        )
        build_report(run)
        run.refresh_from_db()
        self.assertTrue(run.data.startswith(b"PK"))

    def test_a_report_can_be_downloaded(self):
        run = ReportRun.objects.create(
            shop=self.shop, kind=ReportRun.STOCK, format=ReportRun.PDF
        )
        build_report(run)
        response = self.client.get(
            reverse("smst_stocks:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(bytes(response.content).startswith(b"%PDF-"))

    def test_an_employee_sees_the_shop_they_work_at(self):
        from smst_works.models import Employee, Rank

        worker = User.objects.create_user(
            username="amina", email="amina@example.test", password="s3cret-pass-123"
        )
        rank = Rank.objects.create(
            shop=self.shop,
            name="Cleaner",
            permissions=[
                "stocks.view",
                "stocks.view.products",
                "stocks.view.movements",
                "stocks.move",
            ],
        )
        Employee.objects.create(
            shop=self.shop, user=worker, name="Amina", rank=rank
        )
        self._sign_in(worker)

        response = self.client.get(reverse("smst_stocks:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.shop.name)
        self.assertNotContains(response, "Start with the shop")

        response = self.client.get(reverse("smst_stocks:products"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sugar.name)

        response = self.client.get(
            reverse("smst_stocks:stock_product-list"),
            {"shop": self.shop.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def _employee(self, permissions, username="amina"):
        from smst_works.models import Employee, Rank

        worker = User.objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password="s3cret-pass-123",
        )
        rank = Rank.objects.create(
            shop=self.shop,
            name=f"Rank {username}",
            permissions=permissions,
        )
        Employee.objects.create(
            shop=self.shop, user=worker, name=username.title(), rank=rank
        )
        return worker

    def test_a_cleaner_sees_their_own_sale_but_not_a_delivery(self):
        worker = self._employee(
            [
                "stocks.view",
                "stocks.view.products",
                "stocks.view.movements",
                "stocks.move",
            ]
        )
        StockMovement.objects.create(
            product=self.sugar,
            kind=StockMovement.SALE,
            quantity=Decimal("-1"),
            note="Amina sale",
            created_by=worker,
        )
        StockMovement.objects.create(
            product=self.sugar,
            kind=StockMovement.DELIVERY,
            quantity=Decimal("10"),
            note="Owner delivery",
            created_by=worker,
        )
        self._sign_in(worker)

        response = self.client.get(reverse("smst_stocks:movements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amina sale")
        self.assertNotContains(response, "Owner delivery")

        response = self.client.get(
            reverse("smst_stocks:stock_movement-list"),
            {"shop": self.shop.id},
        )
        self.assertEqual(response.status_code, 200)
        notes = [row["note"] for row in response.json()["results"]]
        self.assertIn("Amina sale", notes)
        self.assertNotIn("Owner delivery", notes)

        response = self.client.get(
            reverse("smst_stocks:product_detail", args=[self.sugar.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amina sale")
        self.assertNotContains(response, "Owner delivery")

    def test_an_accountant_sees_the_whole_ledger(self):
        worker = self._employee(
            [
                "stocks.view",
                "stocks.view.movements",
                "stocks.ledger.all",
            ]
        )
        StockMovement.objects.create(
            product=self.sugar,
            kind=StockMovement.SALE,
            quantity=Decimal("-1"),
            note="Amina sale",
            created_by=worker,
        )
        StockMovement.objects.create(
            product=self.sugar,
            kind=StockMovement.DELIVERY,
            quantity=Decimal("10"),
            note="Owner delivery",
            created_by=self.user,
        )
        self._sign_in(worker)

        response = self.client.get(reverse("smst_stocks:movements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amina sale")
        self.assertContains(response, "Owner delivery")

    def test_restricted_stock_pages_are_closed_and_links_hidden(self):
        worker = self._employee(
            [
                "stocks.view",
                "stocks.view.products",
                "stocks.view.movements",
                "stocks.move",
            ]
        )
        self._sign_in(worker)
        for name in ("reports", "shops", "links"):
            response = self.client.get(reverse("smst_stocks:" + name))
            self.assertEqual(response.status_code, 403, name)

        response = self.client.get(reverse("smst_stocks:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("smst_stocks:reports"))
        self.assertNotContains(response, reverse("smst_stocks:shops"))
        self.assertNotContains(response, reverse("smst_stocks:links"))

    def test_downloading_a_stock_report_needs_the_action_permission(self):
        from smst_works.models import Rank

        worker = self._employee(
            ["stocks.view", "stocks.view.reports"]
        )
        run = ReportRun.objects.create(
            shop=self.shop, kind=ReportRun.STOCK, format=ReportRun.PDF
        )
        build_report(run)
        self._sign_in(worker)

        response = self.client.get(reverse("smst_stocks:reports"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, reverse("smst_stocks:report_download", args=[run.id])
        )

        response = self.client.get(
            reverse("smst_stocks:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.get(
            reverse("smst_stocks:report_download_api", args=[run.id])
        )
        self.assertEqual(response.status_code, 403)

        rank = Rank.objects.get(shop=self.shop, name="Rank amina")
        rank.permissions = [*rank.permissions, "stocks.reports.download"]
        rank.save()
        response = self.client.get(
            reverse("smst_stocks:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_the_stock_api_needs_the_page_view_permission(self):
        worker = self._employee(["stocks.view"])
        self._sign_in(worker)
        response = self.client.get(
            reverse("smst_stocks:stock_product-list"),
            {"shop": self.shop.id},
        )
        self.assertEqual(response.status_code, 403)


@override_settings(ROOT_URLCONF="smst_app.urls")
class CartTestCase(TestCase):
    """The cart holds stock, survives a logout, and processes it into the books."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="njeri", email="njeri@example.test", password="s3cret-pass-123"
        )
        self.client = self.client_class(
            SERVER_NAME="app.smst.africa", HTTP_HOST="app.smst.africa"
        )
        self._sign_in(self.user)
        self.shop = Shop.objects.create(owner=self.user, name="Sokoni Traders")
        self.sugar = Product.objects.create(
            shop=self.shop,
            name="Mumias Sugar 1kg",
            buying_price=Decimal("149"),
            selling_price=Decimal("168"),
            quantity=Decimal("24"),
            reorder_level=Decimal("6"),
            unit="piece",
        )

    def _sign_in(self, user):
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = (
            "allauth.account.auth_backends.AuthenticationBackend"
        )
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def test_adding_holds_stock_off_the_shelf(self):
        line = add_to_cart(self.user, self.sugar, 4, CartLine.SELL)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("20"))
        self.assertEqual(line.quantity, Decimal("4"))
        self.assertEqual(line.unit_price, self.sugar.selling_price)
        self.assertTrue(self.sugar.is_in_cart)

    def test_adding_the_same_item_grows_the_line(self):
        add_to_cart(self.user, self.sugar, 4, CartLine.SELL)
        add_to_cart(self.user, self.sugar, 2, CartLine.SELL)
        self.assertEqual(CartLine.objects.filter(user=self.user).count(), 1)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("18"))

    def test_a_buy_and_a_sell_stand_apart(self):
        add_to_cart(self.user, self.sugar, 1, CartLine.SELL)
        add_to_cart(self.user, self.sugar, 1, CartLine.BUY)
        self.assertEqual(CartLine.objects.filter(user=self.user).count(), 2)
        self.assertEqual(
            cart_totals(CartLine.objects.filter(user=self.user))["count"], 2
        )

    def test_a_cart_cannot_hold_more_than_is_in_hand(self):
        with self.assertRaises(StockError):
            add_to_cart(self.user, self.sugar, 100, CartLine.SELL)

    def test_an_out_of_stock_item_is_on_the_shelf_but_cannot_be_sold(self):
        self.sugar.quantity = Decimal("0")
        self.sugar.save(update_fields=["quantity"])

        page = self.client.get(reverse("smst_stocks:cart"))
        self.assertContains(page, self.sugar.name)

        refused = self.client.post(
            reverse("smst_stocks:cart_add"),
            {"product": self.sugar.id, "quantity": 1, "direction": CartLine.SELL},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "in hand")
        self.assertFalse(CartLine.objects.filter(user=self.user).exists())

    def test_an_out_of_stock_item_can_still_be_bought(self):
        self.sugar.quantity = Decimal("0")
        self.sugar.save(update_fields=["quantity"])

        line = add_to_cart(self.user, self.sugar, 4, CartLine.BUY)
        self.assertEqual(line.direction, CartLine.BUY)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("-4"))

        process_cart_line(self.user, line)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("4"))

    def test_releasing_puts_the_stock_back(self):
        line = add_to_cart(self.user, self.sugar, 4, CartLine.SELL)
        release_cart_line(self.user, line)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("24"))
        self.assertFalse(CartLine.objects.filter(pk=line.pk).exists())

    def test_a_cart_cannot_release_what_it_does_not_hold(self):
        line = add_to_cart(self.user, self.sugar, 4, CartLine.SELL)
        other = User.objects.create_user(
            username="otieno", password="s3cret-pass-123"
        )
        with self.assertRaises(StockError):
            release_cart_line(other, line)

    def test_processing_writes_the_movement_and_clears_the_line(self):
        line = add_to_cart(self.user, self.sugar, 3, CartLine.SELL)
        movement = process_cart_line(self.user, line)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("21"))
        self.assertEqual(movement.kind, StockMovement.SALE)
        self.assertEqual(movement.quantity, Decimal("-3"))
        self.assertFalse(CartLine.objects.filter(pk=line.pk).exists())

    def test_processing_a_buy_brings_stock_in(self):
        line = add_to_cart(self.user, self.sugar, 5, CartLine.BUY)
        movement = process_cart_line(self.user, line)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("29"))
        self.assertEqual(movement.kind, StockMovement.DELIVERY)

    def test_processing_posts_the_books(self):
        accounts = ensure_default_accounts(self.shop)
        line = add_to_cart(self.user, self.sugar, 2, CartLine.SELL)
        movement = process_cart_line(self.user, line, account=accounts["cash"])
        entry = FinanceEntry.objects.filter(movement=movement).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, FinanceEntry.INCOME)
        self.assertEqual(entry.amount, Decimal("336"))

    def test_processing_the_whole_cart_posts_every_line(self):
        accounts = ensure_default_accounts(self.shop)
        oil = Product.objects.create(
            shop=self.shop,
            name="Cooking oil 1l",
            buying_price=Decimal("280"),
            selling_price=Decimal("320"),
            quantity=Decimal("10"),
            unit="bottle",
        )
        add_to_cart(self.user, self.sugar, 2, CartLine.SELL)
        add_to_cart(self.user, oil, 3, CartLine.BUY)

        done, failed = process_cart(self.user, self.shop, account=accounts["cash"])

        self.assertEqual(len(done), 2)
        self.assertEqual(failed, [])
        self.assertFalse(CartLine.objects.filter(user=self.user).exists())
        self.assertEqual(
            StockMovement.objects.filter(created_by=self.user).count(), 2
        )
        self.assertEqual(FinanceEntry.objects.filter(shop=self.shop).count(), 2)
        self.sugar.refresh_from_db()
        oil.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("22"))
        self.assertEqual(oil.quantity, Decimal("13"))

    def test_one_set_of_finances_applies_to_every_line(self):
        option = FinanceOption.objects.create(
            shop=self.shop,
            name="Delivery",
            kind=FinanceOption.EXPENSE,
            rate_type=FinanceOption.FIXED,
            rate=Decimal("50"),
        )
        add_to_cart(self.user, self.sugar, 1, CartLine.SELL)
        add_to_cart(self.user, self.sugar, 1, CartLine.BUY)

        process_cart(self.user, self.shop, option_ids=[option.id])

        self.assertEqual(FinanceEntry.objects.filter(option=option).count(), 2)

    def test_processing_the_whole_cart_through_the_url(self):
        add_to_cart(self.user, self.sugar, 2, CartLine.SELL)
        add_to_cart(self.user, self.sugar, 1, CartLine.BUY)

        response = self.client.post(reverse("smst_stocks:cart_process_all"), {})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CartLine.objects.filter(user=self.user).exists())
        self.assertEqual(
            StockMovement.objects.filter(created_by=self.user).count(), 2
        )

    def test_the_cart_offers_one_process_for_all(self):
        line = add_to_cart(self.user, self.sugar, 1, CartLine.SELL)

        page = self.client.get(reverse("smst_stocks:cart"))

        self.assertContains(page, reverse("smst_stocks:cart_process_all"))
        self.assertNotContains(page, reverse("smst_stocks:cart_process", args=[line.id]))
        self.assertContains(page, "Process the line")

    def test_the_cart_survives_a_logout(self):
        add_to_cart(self.user, self.sugar, 2, CartLine.SELL)
        # a new session, as if the person came back after signing out and in
        self.client.cookies.clear()
        self._sign_in(self.user)
        response = self.client.get(reverse("smst_stocks:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sugar.name)
        self.assertEqual(CartLine.objects.filter(user=self.user).count(), 1)

    def test_a_cart_cannot_hold_what_does_not_exist(self):
        stranger = User.objects.create_user(
            username="wekesa", password="s3cret-pass-123"
        )
        other_shop = Shop.objects.create(owner=stranger, name="Elsewhere")
        elsewhere = Product.objects.create(
            shop=other_shop,
            name="Foreign item",
            selling_price=Decimal("10"),
            quantity=Decimal("5"),
        )
        response = self.client.post(
            reverse("smst_stocks:cart_add"),
            {"product": elsewhere.id, "quantity": 1, "direction": CartLine.SELL},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CartLine.objects.filter(user=self.user).exists())

    def test_a_line_is_added_and_processed_through_the_urls(self):
        response = self.client.post(
            reverse("smst_stocks:cart_add"),
            {"product": self.sugar.id, "quantity": 2, "direction": CartLine.SELL},
        )
        self.assertEqual(response.status_code, 302)
        line = CartLine.objects.get(user=self.user, product=self.sugar)
        response = self.client.post(
            reverse("smst_stocks:cart_process", args=[line.id]), {}
        )
        self.assertEqual(response.status_code, 302)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("22"))
        self.assertFalse(CartLine.objects.filter(pk=line.id).exists())

    def test_cart_prices_follow_the_direction(self):
        sell = add_to_cart(self.user, self.sugar, 1, CartLine.SELL)
        buy = add_to_cart(self.user, self.sugar, 1, CartLine.BUY)
        self.assertEqual(sell.unit_price, self.sugar.selling_price)
        self.assertEqual(buy.unit_price, self.sugar.buying_price)

    def test_the_cart_page_wires_up_live_updates_and_lookup(self):
        response = self.client.get(reverse("smst_stocks:cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="cart-live"')
        self.assertContains(response, 'hx-target="#cart-live"')
        self.assertContains(response, 'id="cart-search"')
        self.assertContains(response, 'id="cart-code"')

    def test_a_scanned_code_adds_a_selling_line(self):
        self.sugar.sku = "SUG-1KG"
        self.sugar.save(update_fields=["sku"])

        response = self.client.post(
            reverse("smst_stocks:cart_scan"), {"code": "sug-1kg"}
        )

        self.assertEqual(response.status_code, 302)
        line = CartLine.objects.get(user=self.user)
        self.assertEqual(line.direction, CartLine.SELL)
        self.assertEqual(line.quantity, Decimal("1"))
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.quantity, Decimal("23"))

    def test_an_unknown_code_leaves_the_cart_alone(self):
        response = self.client.post(
            reverse("smst_stocks:cart_scan"), {"code": "nope"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CartLine.objects.filter(user=self.user).exists())

    def test_adding_from_the_cart_answers_with_the_live_cart(self):
        response = self.client.post(
            reverse("smst_stocks:cart_add"),
            {"product": self.sugar.id, "quantity": 2, "direction": CartLine.SELL},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "smst_stocks/partials/cart_live.html")
        self.assertContains(response, self.sugar.name)
        self.assertEqual(CartLine.objects.filter(user=self.user).count(), 1)

    def test_processing_from_the_cart_returns_a_saved_receipt(self):
        line = add_to_cart(self.user, self.sugar, 2, CartLine.SELL)

        response = self.client.post(
            reverse("smst_stocks:cart_process", args=[line.id]),
            {},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "smst_stocks/partials/cart_live.html")
        self.assertFalse(CartLine.objects.filter(pk=line.pk).exists())
        receipt = Receipt.objects.get(shop=self.shop)
        self.assertTrue(receipt.data.startswith(b"%PDF"))
        self.assertEqual(receipt.details["product"], self.sugar.name)
        self.assertIn("receipt:print", response["HX-Trigger"])

    def test_a_saved_receipt_can_be_downloaded(self):
        line = add_to_cart(self.user, self.sugar, 1, CartLine.SELL)
        movement = process_cart_line(self.user, line)
        receipt = finance_bridge.receipts().create_receipt(line, movement, self.user)

        response = self.client.get(
            reverse("smst_finances:receipt_download", args=[receipt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_saved_receipts_have_a_page_and_a_print_view(self):
        line = add_to_cart(self.user, self.sugar, 2, CartLine.SELL)
        movement = process_cart_line(self.user, line)
        receipt = finance_bridge.receipts().create_receipt(line, movement, self.user)

        listing = self.client.get(reverse("smst_finances:receipts"))
        printing = self.client.get(
            reverse("smst_finances:receipt_print", args=[receipt.id])
        )

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, receipt.reference)
        self.assertEqual(printing.status_code, 200)
        self.assertContains(printing, self.sugar.name)
        self.assertContains(printing, self.shop.currency)
