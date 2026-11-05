"""Tests for SmSt Finances.

The app keeps the money side of a shop. These tests follow one small shop all
the way in: a chart of accounts, entries linked to stock movements, balanced
statements, budgets, graphs and the report files.
"""

from decimal import Decimal

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

from smst_stocks.models import Product, Shop, StockMovement

from .models import (
    FinanceAccount,
    FinanceBudget,
    FinanceChart,
    FinanceEntry,
    FinanceOption,
    FinanceReport,
    JournalLine,
)
from .reports.builder import build_report
from .services import (
    FinanceError,
    account_balance,
    balance_sheet,
    budget_status,
    chart_data,
    create_entry,
    dashboard_summary,
    default_account,
    ensure_default_accounts,
    entry_summary,
    link_stock_movement,
    money_accounts,
    profit_and_loss,
    sync_stock_movement,
    trial_balance,
    void_entry,
)

User = get_user_model()


@override_settings(ROOT_URLCONF="smst_ai.urls")
class FinanceTestCase(TestCase):
    """A shop with two items, and the owner of it."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="njeri", email="njeri@example.test", password="s3cret-pass-123"
        )
        # the app lives on the app host, so the tests are run as that host
        self.client = self.client_class(
            SERVER_NAME="app.smartstock.africa", HTTP_HOST="app.smartstock.africa"
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
        """Sign the user in without going through the login form."""
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = (
            "allauth.account.auth_backends.AuthenticationBackend"
        )
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def _movement(self, kind, quantity, product=None, user=None):
        product = product or self.sugar
        return StockMovement.objects.create(
            product=product,
            kind=kind,
            quantity=Decimal(str(quantity)),
            created_by=user or self.user,
        )

    # ------------------------------------------------------------- models
    def test_the_chart_of_accounts_is_seeded(self):
        roles = ensure_default_accounts(self.shop)
        self.assertIn("cash", roles)
        self.assertIn("sales", roles)
        self.assertIn("tax_payable", roles)
        self.assertEqual(
            FinanceAccount.objects.filter(shop=self.shop).count(),
            len(roles),
        )
        # running it again changes nothing
        ensure_default_accounts(self.shop)
        self.assertEqual(
            FinanceAccount.objects.filter(shop=self.shop).count(), len(roles)
        )

    def test_the_normal_balance_follows_the_type(self):
        roles = ensure_default_accounts(self.shop)
        self.assertEqual(roles["cash"].normal_balance, "debit")
        self.assertEqual(roles["sales"].normal_balance, "credit")
        self.assertEqual(roles["operating"].normal_balance, "debit")

    def test_a_percentage_option_takes_its_rate(self):
        option = FinanceOption.objects.create(
            shop=self.shop,
            name="VAT 16%",
            kind=FinanceOption.TAX,
            rate_type=FinanceOption.PERCENTAGE,
            rate=Decimal("16"),
        )
        self.assertEqual(option.amount_for(Decimal("1000")), Decimal("160.00"))

    def test_a_fixed_option_takes_its_amount(self):
        option = FinanceOption.objects.create(
            shop=self.shop,
            name="Delivery fee",
            kind=FinanceOption.EXPENSE,
            rate_type=FinanceOption.FIXED,
            rate=Decimal("150"),
        )
        self.assertEqual(option.amount_for(Decimal("1000")), Decimal("150.00"))

    # ----------------------------------------------------------- services
    def test_an_income_entry_posts_two_balanced_lines(self):
        entry = create_entry(
            self.shop,
            {
                "kind": FinanceEntry.INCOME,
                "amount": Decimal("500"),
                "description": "Counter sale",
            },
            user=self.user,
        )
        self.assertEqual(entry.lines.count(), 2)
        debit = sum((line.debit for line in entry.lines.all()), Decimal("0"))
        credit = sum((line.credit for line in entry.lines.all()), Decimal("0"))
        self.assertEqual(debit, credit)
        self.assertEqual(debit, Decimal("500.00"))
        self.assertEqual(entry.amount, Decimal("500.00"))

    def test_an_entry_needs_an_amount_or_a_movement(self):
        with self.assertRaises(FinanceError):
            create_entry(
                self.shop,
                {"kind": FinanceEntry.EXPENSE, "description": "Something"},
            )

    def test_an_entry_needs_a_description(self):
        with self.assertRaises(FinanceError):
            create_entry(self.shop, {"kind": FinanceEntry.INCOME, "amount": "10"})

    def test_profit_from_a_movement_is_the_margin(self):
        movement = self._movement(StockMovement.SALE, -3)
        entry = link_stock_movement(self.shop, movement.id, FinanceEntry.PROFIT)
        # three pieces at a margin of 168 - 149 = 19
        self.assertEqual(entry.amount, Decimal("57.00"))
        self.assertEqual(entry.source, FinanceEntry.STOCK)
        self.assertEqual(entry.movement_id, movement.id)

    def test_a_loss_comes_out_of_stock_not_the_till(self):
        movement = self._movement(StockMovement.LOSS, -2)
        entry = link_stock_movement(self.shop, movement.id, FinanceEntry.LOSS)
        self.assertEqual(entry.amount, Decimal("298.00"))
        inventory = default_account(self.shop, "inventory")
        self.assertTrue(
            entry.lines.filter(account=inventory).exists()
        )

    # --------------------------------------------------- stock integration
    def test_the_movement_form_lists_only_asset_accounts(self):
        accounts = money_accounts(self.shop)
        self.assertTrue(accounts)
        self.assertTrue(
            all(account.type == FinanceAccount.ASSET for account in accounts)
        )
        self.assertEqual(accounts[0].code, "1000")

    def test_a_sale_movement_posts_money_in(self):
        movement = self._movement(StockMovement.SALE, -4)
        cash = default_account(self.shop, "cash")
        entry = sync_stock_movement(movement, account=cash)
        self.assertEqual(entry.kind, FinanceEntry.INCOME)
        self.assertEqual(entry.amount, Decimal("672.00"))
        self.assertEqual(entry.account.code, "4000")
        self.assertEqual(entry.payment_account, cash)
        self.assertEqual(account_balance(cash), Decimal("672.00"))

    def test_a_delivery_movement_posts_money_out(self):
        movement = self._movement(StockMovement.DELIVERY, 5)
        bank = default_account(self.shop, "bank")
        entry = sync_stock_movement(movement, account=bank)
        self.assertEqual(entry.kind, FinanceEntry.EXPENSE)
        self.assertEqual(entry.amount, Decimal("745.00"))
        self.assertEqual(entry.account.code, "1200")
        self.assertEqual(account_balance(bank), Decimal("-745.00"))

    def test_a_movement_without_an_account_does_not_post(self):
        movement = self._movement(StockMovement.SALE, -1)
        self.assertIsNone(sync_stock_movement(movement))
        self.assertEqual(FinanceEntry.objects.count(), 0)

    def test_syncing_again_updates_the_same_entry(self):
        movement = self._movement(StockMovement.SALE, -2)
        cash = default_account(self.shop, "cash")
        first = sync_stock_movement(movement, account=cash)
        second = sync_stock_movement(movement, account=cash)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FinanceEntry.objects.count(), 1)

    def test_a_tax_entry_lands_in_tax_payable(self):
        entry = create_entry(
            self.shop,
            {
                "kind": FinanceEntry.TAX,
                "amount": Decimal("160"),
                "description": "VAT collected",
            },
        )
        tax_payable = default_account(self.shop, "tax_payable")
        line = entry.lines.get(account=tax_payable)
        self.assertEqual(line.credit, Decimal("160.00"))

    def test_a_tax_option_on_a_sale_adds_the_tax_on_top(self):
        option = FinanceOption.objects.create(
            shop=self.shop,
            name="VAT 16%",
            kind=FinanceOption.TAX,
            rate_type=FinanceOption.PERCENTAGE,
            rate=Decimal("16"),
        )
        entry = create_entry(
            self.shop,
            {
                "kind": FinanceEntry.INCOME,
                "option": option,
                "amount": Decimal("2000"),
                "description": "Groceries",
            },
        )

        self.assertEqual(entry.kind, FinanceEntry.INCOME)
        self.assertEqual(entry.amount, Decimal("2000.00"))
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "cash")).debit,
            Decimal("2320.00"),
        )
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "sales")).credit,
            Decimal("2000.00"),
        )
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "tax_payable")).credit,
            Decimal("320.00"),
        )
        self.assertEqual(dashboard_summary(self.shop)["tax_due"], Decimal("320.00"))
        self.assertEqual(entry_summary(self.shop)["tax"], Decimal("320.00"))

    def test_an_inclusive_tax_is_taken_out_of_the_amount(self):
        option = FinanceOption.objects.create(
            shop=self.shop,
            name="VAT 16% included",
            kind=FinanceOption.TAX,
            rate_type=FinanceOption.PERCENTAGE_INCLUDED,
            rate=Decimal("16"),
        )
        entry = create_entry(
            self.shop,
            {
                "kind": FinanceEntry.INCOME,
                "option": option,
                "amount": Decimal("18000"),
                "description": "A phone",
            },
        )

        self.assertEqual(entry.amount, Decimal("18000.00"))
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "cash")).debit,
            Decimal("18000.00"),
        )
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "sales")).credit,
            Decimal("15517.24"),
        )
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "tax_payable")).credit,
            Decimal("2482.76"),
        )

    def test_a_tax_option_on_an_expense_keeps_the_spend_and_adds_tax(self):
        option = FinanceOption.objects.create(
            shop=self.shop,
            name="VAT 200",
            kind=FinanceOption.TAX,
            rate_type=FinanceOption.FIXED,
            rate=Decimal("200"),
        )
        entry = create_entry(
            self.shop,
            {
                "kind": FinanceEntry.EXPENSE,
                "option": option,
                "amount": Decimal("2000"),
                "description": "Groceries from the supplier",
            },
        )

        self.assertEqual(entry.kind, FinanceEntry.EXPENSE)
        self.assertEqual(entry.amount, Decimal("2000.00"))
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "operating")).debit,
            Decimal("2000.00"),
        )
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "tax_payable")).debit,
            Decimal("200.00"),
        )
        self.assertEqual(
            entry.lines.get(account=default_account(self.shop, "cash")).credit,
            Decimal("2200.00"),
        )
        # The tax was paid out, so it lowers what the shop owes.
        self.assertEqual(dashboard_summary(self.shop)["tax_due"], Decimal("-200.00"))
        self.assertEqual(entry_summary(self.shop)["tax"], Decimal("-200.00"))
        self.assertEqual(entry_summary(self.shop)["expense"], Decimal("2000.00"))

    def test_a_movement_from_another_shop_is_refused(self):
        other = User.objects.create_user(
            username="amina", email="amina@example.test", password="s3cret-pass-123"
        )
        other_shop = Shop.objects.create(owner=other, name="Bluewave Agro")
        other_product = Product.objects.create(
            shop=other_shop, name="Secret Item", selling_price=Decimal("10")
        )
        movement = StockMovement.objects.create(
            product=other_product, kind=StockMovement.SALE, quantity=Decimal("-1")
        )
        with self.assertRaises(FinanceError):
            link_stock_movement(self.shop, movement.id, FinanceEntry.PROFIT)

    def test_voiding_an_entry_clears_its_lines(self):
        entry = create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "100", "description": "Sale"},
        )
        self.assertEqual(entry.lines.count(), 2)
        void_entry(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, FinanceEntry.VOID)
        self.assertEqual(entry.lines.count(), 0)

    def test_the_entry_summary_totals_the_book(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        create_entry(
            self.shop,
            {"kind": FinanceEntry.EXPENSE, "amount": "447", "description": "Bill"},
        )
        summary = entry_summary(self.shop)
        self.assertEqual(summary["income"], Decimal("504.00"))
        self.assertEqual(summary["expense"], Decimal("447.00"))
        self.assertEqual(summary["net"], Decimal("57.00"))
        self.assertEqual(summary["count"], 2)

    def test_the_dashboard_summary_reads_the_balances(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        summary = dashboard_summary(self.shop)
        self.assertEqual(summary["cash"], Decimal("504.00"))
        self.assertEqual(summary["products"], 2)
        self.assertEqual(summary["stock_amount"], Decimal("7112.00"))

    # ---------------------------------------------------------- statements
    def test_the_trial_balance_agrees(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        create_entry(
            self.shop,
            {"kind": FinanceEntry.EXPENSE, "amount": "447", "description": "Bill"},
        )
        trial = trial_balance(self.shop)
        self.assertTrue(trial["balanced"])
        self.assertEqual(trial["total_debit"], trial["total_credit"])

    def test_the_balance_sheet_balances(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        create_entry(
            self.shop,
            {"kind": FinanceEntry.EXPENSE, "amount": "447", "description": "Bill"},
        )
        sheet = balance_sheet(self.shop)
        self.assertTrue(sheet["balanced"])
        self.assertEqual(
            sheet["assets_total"],
            sheet["liabilities_total"] + sheet["equity_total"],
        )

    def test_the_profit_and_loss_shows_the_net(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        create_entry(
            self.shop,
            {"kind": FinanceEntry.EXPENSE, "amount": "447", "description": "Bill"},
        )
        pnl = profit_and_loss(self.shop)
        self.assertEqual(pnl["income_total"], Decimal("504.00"))
        self.assertEqual(pnl["expense_total"], Decimal("447.00"))
        self.assertEqual(pnl["net"], Decimal("57.00"))

    # -------------------------------------------------------------- charts
    def test_a_chart_can_plot_values_that_were_typed(self):
        data = chart_data(
            self.shop,
            x_values=["January", "February", "March"],
            y_values=["12000", "18500", "21400"],
        )
        self.assertEqual(data["labels"], ["January", "February", "March"])
        self.assertEqual(
            data["values"],
            [Decimal("12000.00"), Decimal("18500.00"), Decimal("21400.00")],
        )
        self.assertEqual(data["x_source"], FinanceChart.CUSTOM)

    def test_a_chart_can_put_stock_value_against_time(self):
        data = chart_data(
            self.shop,
            x_source=FinanceChart.TIME,
            y_source=FinanceChart.STOCK_AMOUNT,
            date_from="2026-10-01",
            date_to="2026-10-07",
        )
        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["values"]), 7)
        # 24 pieces at 168 plus 8 at 385, unchanged over the week
        self.assertEqual(data["values"][0], Decimal("7112.00"))

    # ------------------------------------------------------------- budgets
    def test_a_budget_measures_what_was_spent(self):
        roles = ensure_default_accounts(self.shop)
        create_entry(
            self.shop,
            {"kind": FinanceEntry.EXPENSE, "amount": "600", "description": "Rent"},
        )
        budget = FinanceBudget.objects.create(
            shop=self.shop,
            name="Monthly costs",
            account=roles["operating"],
            period=FinanceBudget.MONTHLY,
            amount=Decimal("1000"),
        )
        status = budget_status(budget)
        self.assertEqual(status["spent"], Decimal("600.00"))
        self.assertEqual(status["remaining"], Decimal("400.00"))
        self.assertEqual(status["percent"], 60.0)

    # ----------------------------------------------------------------- api
    def test_the_pages_open(self):
        for name in [
            "smst_finances:dashboard",
            "smst_finances:entries",
            "smst_finances:options",
            "smst_finances:accounts",
            "smst_finances:statements",
            "smst_finances:charts",
            "smst_finances:budgets",
            "smst_finances:reports",
        ]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_the_dashboard_shows_the_figures(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        response = self.client.get(reverse("smst_finances:dashboard"))
        body = response.content.decode()
        self.assertIn('data-stat="income"', body)
        self.assertIn('data-stat="expense"', body)
        self.assertIn("Ksh", body)

    def test_the_rail_can_be_collapsed(self):
        response = self.client.get(reverse("smst_finances:dashboard"))
        body = response.content.decode()
        self.assertIn("data-rail-toggle", body)
        self.assertIn('aria-expanded="true"', body)
        self.assertIn('data-label="Dashboard"', body)
        self.assertIn('aria-current="page"', body)

    def test_creating_an_entry_through_the_api(self):
        response = self.client.post(
            reverse("smst_finances:finance_entry-list"),
            {
                "shop": self.shop.id,
                "kind": "income",
                "amount": "504",
                "description": "Counter sale",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        entry = FinanceEntry.objects.get()
        self.assertEqual(entry.lines.count(), 2)
        self.assertTrue(entry.is_posted)

    def test_an_entry_without_a_description_is_refused(self):
        response = self.client.post(
            reverse("smst_finances:finance_entry-list"),
            {"shop": self.shop.id, "kind": "income", "amount": "10"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(FinanceEntry.objects.count(), 0)

    def test_an_entry_can_be_voided_through_the_api(self):
        entry = create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "100", "description": "Sale"},
        )
        response = self.client.post(
            reverse("smst_finances:finance_entry-void", args=[entry.id]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "void")

    def test_creating_an_option_and_an_account(self):
        response = self.client.post(
            reverse("smst_finances:finance_option-list"),
            {
                "shop": self.shop.id,
                "name": "VAT 16%",
                "kind": "tax",
                "rate_type": "percentage",
                "rate": "16",
                "applies_to": "sale",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["rate"], "16.0000")

        response = self.client.post(
            reverse("smst_finances:finance_account-list"),
            {
                "shop": self.shop.id,
                "code": "7000",
                "name": "Bank charges",
                "type": "expense",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            FinanceAccount.objects.filter(shop=self.shop, code="7000").exists()
        )

    def test_creating_a_budget(self):
        response = self.client.post(
            reverse("smst_finances:finance_budget-list"),
            {
                "shop": self.shop.id,
                "name": "Monthly costs",
                "period": "monthly",
                "amount": "1000",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("status", response.json())

    def test_creating_and_previewing_a_graph(self):
        response = self.client.post(
            reverse("smst_finances:finance_chart-list"),
            {
                "shop": self.shop.id,
                "title": "Typed figures",
                "chart_type": "bar",
                "x_source": "custom",
                "y_source": "custom",
                "x_values": ["Jan", "Feb"],
                "y_values": ["10", "20"],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            reverse("smst_finances:finance_chart-preview"),
            {
                "shop": self.shop.id,
                "x_source": "time",
                "y_source": "income",
                "date_from": "2026-10-01",
                "date_to": "2026-10-03",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["labels"]), 3)

    def test_a_graph_with_unbalanced_typed_values_is_refused(self):
        response = self.client.post(
            reverse("smst_finances:finance_chart-list"),
            {
                "shop": self.shop.id,
                "title": "Broken",
                "chart_type": "bar",
                "x_source": "custom",
                "y_source": "custom",
                "x_values": ["Jan", "Feb"],
                "y_values": ["10"],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_the_summary_and_statements_are_served(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        summary = self.client.get(reverse("smst_finances:api_summary"))
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["income"], "504.00")

        statements = self.client.get(
            reverse("smst_finances:api_statements"), {"kind": "trial_balance"}
        )
        self.assertEqual(statements.status_code, 200)
        self.assertTrue(statements.json()["balanced"])

    def test_another_shops_entry_is_hidden(self):
        other = User.objects.create_user(
            username="amina", email="amina@example.test", password="s3cret-pass-123"
        )
        other_shop = Shop.objects.create(owner=other, name="Bluewave Agro")
        entry = create_entry(
            other_shop,
            {"kind": FinanceEntry.INCOME, "amount": "10", "description": "Theirs"},
        )
        response = self.client.get(
            reverse("smst_finances:finance_entry-detail", args=[entry.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_the_journal_lines_are_kept_in_the_database(self):
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        self.assertEqual(JournalLine.objects.count(), 2)
        self.assertEqual(
            sum((line.debit for line in JournalLine.objects.all()), Decimal("0")),
            Decimal("504.00"),
        )

    # ------------------------------------------------------------- reports
    def test_the_reports_build(self):
        kinds = [
            FinanceReport.INCOME,
            FinanceReport.EXPENSES,
            FinanceReport.PROFIT_LOSS,
            FinanceReport.TAX,
            FinanceReport.CASH_FLOW,
            FinanceReport.TRIAL_BALANCE,
            FinanceReport.BALANCE_SHEET,
            FinanceReport.GENERAL_LEDGER,
            FinanceReport.BUDGETS,
        ]
        create_entry(
            self.shop,
            {"kind": FinanceEntry.INCOME, "amount": "504", "description": "Sale"},
        )
        for kind in kinds:
            for report_format in [FinanceReport.PDF, FinanceReport.XLSX]:
                run = FinanceReport.objects.create(
                    shop=self.shop,
                    kind=kind,
                    format=report_format,
                    created_by=self.user,
                )
                build_report(run)
                run.refresh_from_db()
                self.assertEqual(run.status, FinanceReport.READY, kind)
                self.assertTrue(run.content, kind)
                self.assertTrue(
                    run.filename.endswith(
                        ".pdf" if report_format == FinanceReport.PDF else ".xlsx"
                    )
                )

    def test_the_pdf_is_a_pdf(self):
        run = FinanceReport.objects.create(
            shop=self.shop, kind=FinanceReport.PROFIT_LOSS, format=FinanceReport.PDF
        )
        build_report(run)
        run.refresh_from_db()
        self.assertTrue(run.data.startswith(b"%PDF-"))

    def test_the_workbook_is_a_zip(self):
        run = FinanceReport.objects.create(
            shop=self.shop, kind=FinanceReport.PROFIT_LOSS, format=FinanceReport.XLSX
        )
        build_report(run)
        run.refresh_from_db()
        self.assertTrue(run.data.startswith(b"PK"))

    def test_a_report_can_be_downloaded(self):
        run = FinanceReport.objects.create(
            shop=self.shop, kind=FinanceReport.PROFIT_LOSS, format=FinanceReport.PDF
        )
        build_report(run)
        response = self.client.get(
            reverse("smst_finances:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(bytes(response.content).startswith(b"%PDF-"))

    def test_a_report_that_is_not_ready_is_a_404(self):
        run = FinanceReport.objects.create(
            shop=self.shop, kind=FinanceReport.PROFIT_LOSS, format=FinanceReport.PDF
        )
        response = self.client.get(
            reverse("smst_finances:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------- wiring
    def test_the_websocket_group_names_the_owner(self):
        from .realtime import shop_group

        self.assertEqual(shop_group("njeri"), "smst_finances_njeri")

    def test_the_api_needs_a_signed_in_user(self):
        anonymous = self.client_class(
            SERVER_NAME="app.smartstock.africa", HTTP_HOST="app.smartstock.africa"
        )
        response = anonymous.get(reverse("smst_finances:finance_entry-list"))
        self.assertIn(response.status_code, (401, 403))

    def test_an_employee_sees_the_shop_they_work_at(self):
        from smst_works.models import Employee, Rank

        worker = User.objects.create_user(
            username="amina", email="amina@example.test", password="s3cret-pass-123"
        )
        rank = Rank.objects.create(
            shop=self.shop,
            name="Accountant",
            permissions=[
                "stocks.view",
                "finances.view.dashboard",
                "finances.view.entries",
                "customers.manage",
            ],
        )
        Employee.objects.create(
            shop=self.shop, user=worker, name="Amina", rank=rank
        )
        self._sign_in(worker)

        response = self.client.get(reverse("smst_finances:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.shop.name)
        self.assertNotContains(response, "Start with the shop")

        response = self.client.get(
            reverse("smst_finances:api_summary"), {"shop": self.shop.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["products"], 2)

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

    def test_a_cleaner_only_sees_their_own_finance_entries(self):
        worker = self._employee(["finances.view.entries"])
        FinanceEntry.objects.create(
            shop=self.shop,
            kind=FinanceEntry.EXPENSE,
            amount=Decimal("10"),
            description="Amina entry",
            created_by=worker,
        )
        FinanceEntry.objects.create(
            shop=self.shop,
            kind=FinanceEntry.EXPENSE,
            amount=Decimal("20"),
            description="Owner entry",
            created_by=self.user,
        )
        self._sign_in(worker)

        response = self.client.get(reverse("smst_finances:entries"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amina entry")
        self.assertNotContains(response, "Owner entry")

        response = self.client.get(
            reverse("smst_finances:finance_entry-list"),
            {"shop": self.shop.id},
        )
        self.assertEqual(response.status_code, 200)
        descriptions = [
            row["description"] for row in response.json()["results"]
        ]
        self.assertIn("Amina entry", descriptions)
        self.assertNotIn("Owner entry", descriptions)

    def test_restricted_finance_pages_are_closed_and_links_hidden(self):
        worker = self._employee(["finances.view.entries"])
        self._sign_in(worker)
        for name in (
            "dashboard",
            "statements",
            "reports",
            "options",
            "accounts",
            "charts",
            "budgets",
        ):
            response = self.client.get(reverse("smst_finances:" + name))
            self.assertEqual(response.status_code, 403, name)

        response = self.client.get(reverse("smst_finances:entries"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/smst_finances/"')

    def test_graph_generation_needs_the_action_permission(self):
        from smst_works.models import Rank

        worker = self._employee(["finances.view.charts"])
        self._sign_in(worker)

        response = self.client.get(reverse("smst_finances:charts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not generate new ones")

        preview = {
            "shop": self.shop.id,
            "x_source": "time",
            "y_source": "income",
            "date_from": "2026-10-01",
            "date_to": "2026-10-03",
        }
        response = self.client.post(
            reverse("smst_finances:finance_chart-preview"),
            preview,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        rank = Rank.objects.get(shop=self.shop, name="Rank amina")
        rank.permissions = [*rank.permissions, "finances.graphs.generate"]
        rank.save()
        response = self.client.post(
            reverse("smst_finances:finance_chart-preview"),
            preview,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_downloading_a_finance_report_needs_the_action_permission(self):
        from smst_works.models import Rank

        worker = self._employee(["finances.view.reports"])
        run = FinanceReport.objects.create(
            shop=self.shop,
            kind=FinanceReport.PROFIT_LOSS,
            format=FinanceReport.PDF,
        )
        build_report(run)
        self._sign_in(worker)

        response = self.client.get(reverse("smst_finances:reports"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse("smst_finances:report_download", args=[run.id]),
        )

        response = self.client.get(
            reverse("smst_finances:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 403)

        rank = Rank.objects.get(shop=self.shop, name="Rank amina")
        rank.permissions = [*rank.permissions, "finances.reports.download"]
        rank.save()
        response = self.client.get(
            reverse("smst_finances:report_download", args=[run.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_the_finance_api_needs_the_page_view_permission(self):
        worker = self._employee(["finances.view.entries"])
        self._sign_in(worker)
        response = self.client.get(
            reverse("smst_finances:finance_account-list"),
            {"shop": self.shop.id},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.get(
            reverse("smst_finances:finance_entry-list"),
            {"shop": self.shop.id},
        )
        self.assertEqual(response.status_code, 200)
