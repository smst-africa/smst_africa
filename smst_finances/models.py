"""Models for SmSt Finances.

The app keeps the money side of a shop. Finance options describe the rules a
shop uses (a tax rate, a discount, a delivery expense). Finance entries are the
book: every entry posts a balanced pair of lines into the chart of accounts, so
the statements can be read straight from the same records that the shopkeeper
sees on screen.

Entries can be tied to a product and to a stock movement in SmSt Stocks. That
is how a sale carries its profit, and how a damaged or lost item carries its
cost, without the two apps ever disagreeing.
"""

from __future__ import annotations

import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

ZERO = Decimal("0.00")


def generate_token(length: int = 6) -> str:
    return secrets.token_hex(length).upper()


def generate_reference() -> str:
    return f"FN-{generate_token(4)}"


def generate_receipt_reference() -> str:
    return f"RC-{generate_token(4)}"


class FinanceAccount(models.Model):
    """One account in a shop's chart of accounts."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"

    TYPE_CHOICES = (
        (ASSET, "Asset"),
        (LIABILITY, "Liability"),
        (EQUITY, "Equity"),
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="finance_accounts"
    )
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=EXPENSE)
    description = models.CharField(max_length=240, blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("type", "code")
        unique_together = ("shop", "code")
        indexes = [
            models.Index(fields=["shop", "type"]),
            models.Index(fields=["shop", "code"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    @property
    def normal_balance(self) -> str:
        """The side that increases this account."""
        return "debit" if self.type in (self.ASSET, self.EXPENSE) else "credit"

    @property
    def balance(self):
        from .services import account_balance

        return account_balance(self)


class FinanceOption(models.Model):
    """A rule the shop applies to money: a tax, a discount or an expense."""

    TAX = "tax"
    DISCOUNT = "discount"
    EXPENSE = "expense"
    INCOME = "income"
    FEE = "fee"
    REFUND = "refund"
    OTHER = "other"

    KIND_CHOICES = (
        (TAX, "Tax"),
        (DISCOUNT, "Discount"),
        (EXPENSE, "Expense"),
        (INCOME, "Income"),
        (FEE, "Fee"),
        (REFUND, "Refund"),
        (OTHER, "Other"),
    )

    FIXED = "fixed"
    PERCENTAGE = "percentage"
    # Short on purpose: it fits the existing 16-char column, so no migration.
    PERCENTAGE_INCLUDED = "included"

    RATE_TYPE_CHOICES = (
        (FIXED, "Fixed amount"),
        (PERCENTAGE, "Percentage"),
        (PERCENTAGE_INCLUDED, "Percentage, already inside the amount"),
    )

    SALE = "sale"
    PURCHASE = "purchase"
    MOVEMENT = "movement"
    EXPENSE_USE = "expense"
    ALL = "all"

    APPLIES_TO_CHOICES = (
        (SALE, "Sales"),
        (PURCHASE, "Purchases"),
        (MOVEMENT, "Stock movements"),
        (EXPENSE_USE, "Expenses"),
        (ALL, "Everything"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="finance_options"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=EXPENSE)
    description = models.CharField(max_length=240, blank=True)
    rate_type = models.CharField(
        max_length=16, choices=RATE_TYPE_CHOICES, default=FIXED
    )
    rate = models.DecimalField(max_digits=10, decimal_places=4, default=ZERO)
    applies_to = models.CharField(
        max_length=16, choices=APPLIES_TO_CHOICES, default=ALL
    )
    account = models.ForeignKey(
        FinanceAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="options",
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("kind", "name")
        unique_together = ("shop", "name")
        indexes = [
            models.Index(fields=["shop", "kind"]),
            models.Index(fields=["shop", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()})"

    def amount_for(self, base_amount) -> Decimal:
        """What this rule takes from a base amount."""
        try:
            base = Decimal(str(base_amount or 0))
        except (TypeError, ValueError, ArithmeticError):
            base = ZERO
        if self.rate_type == self.PERCENTAGE:
            return (base * Decimal(str(self.rate or 0)) / Decimal("100")).quantize(
                Decimal("0.01")
            )
        if self.rate_type == self.PERCENTAGE_INCLUDED:
            rate = Decimal(str(self.rate or 0))
            if rate <= 0:
                return ZERO
            return (base * rate / (Decimal("100") + rate)).quantize(Decimal("0.01"))
        return Decimal(str(self.rate or 0)).quantize(Decimal("0.01"))

    def tax_for(self, base_amount) -> Decimal:
        """The tax already inside an amount, or nil when the option adds it on top."""
        try:
            base = Decimal(str(base_amount or 0))
        except (TypeError, ValueError, ArithmeticError):
            base = ZERO
        if self.rate_type != self.PERCENTAGE_INCLUDED:
            return ZERO
        return min(self.amount_for(base), base)


class FinanceEntry(models.Model):
    """One money event, linked to the accounts it moved."""

    INCOME = "income"
    EXPENSE = "expense"
    TAX = "tax"
    DISCOUNT = "discount"
    PROFIT = "profit"
    LOSS = "loss"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"

    KIND_CHOICES = (
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
        (TAX, "Tax"),
        (DISCOUNT, "Discount"),
        (PROFIT, "Profit from a sale"),
        (LOSS, "Loss or damage"),
        (REFUND, "Refund or return"),
        (ADJUSTMENT, "Adjustment"),
    )

    DRAFT = "draft"
    POSTED = "posted"
    VOID = "void"

    STATUS_CHOICES = (
        (DRAFT, "Draft"),
        (POSTED, "Posted"),
        (VOID, "Void"),
    )

    MANUAL = "manual"
    STOCK = "stock"
    ORDER = "order"

    SOURCE_CHOICES = (
        (MANUAL, "Entered by hand"),
        (STOCK, "Stock movement"),
        (ORDER, "Order"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="finance_entries"
    )
    option = models.ForeignKey(
        FinanceOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entries",
    )
    product = models.ForeignKey(
        "smst_stocks.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_entries",
    )
    movement = models.ForeignKey(
        "smst_stocks.StockMovement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_entries",
    )
    order = models.ForeignKey(
        "smst_stocks.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_entries",
    )
    account = models.ForeignKey(
        FinanceAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entries",
        help_text="The income, expense, tax or balance account this entry belongs to.",
    )
    payment_account = models.ForeignKey(
        FinanceAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="The cash or bank account the money moved through.",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=EXPENSE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=POSTED)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=MANUAL)
    reference = models.CharField(
        max_length=24, unique=True, default=generate_reference, editable=False
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    base_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="The sale, purchase or expense the option was applied to.",
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="The rate used, kept with the entry so old books never change.",
    )
    description = models.CharField(max_length=240)
    note = models.CharField(max_length=240, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [
            models.Index(fields=["shop", "-occurred_at"]),
            models.Index(fields=["shop", "kind"]),
            models.Index(fields=["shop", "status"]),
            models.Index(fields=["product", "-occurred_at"]),
            models.Index(fields=["movement"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.description}"

    @property
    def is_posted(self) -> bool:
        return self.status == self.POSTED

    @property
    def signed_amount(self):
        """Positive for money in, negative for money out."""
        if self.kind in (self.INCOME, self.PROFIT):
            return self.amount
        return -self.amount

    @property
    def movement_label(self) -> str:
        if not self.movement:
            return ""
        return (
            f"{self.movement.get_kind_display()} · "
            f"{self.movement.quantity:g} · {self.movement.product.name}"
        )


class JournalLine(models.Model):
    """One side of a double-entry posting."""

    entry = models.ForeignKey(
        FinanceEntry, on_delete=models.CASCADE, related_name="lines"
    )
    account = models.ForeignKey(
        FinanceAccount, on_delete=models.PROTECT, related_name="journal_lines"
    )
    description = models.CharField(max_length=240, blank=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["account", "entry"])]

    def __str__(self) -> str:
        return f"{self.account.code} Dr {self.debit} Cr {self.credit}"

    @property
    def signed(self) -> Decimal:
        return self.debit - self.credit


class FinanceBudget(models.Model):
    """A spending plan for a period, measured against posted entries."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

    PERIOD_CHOICES = (
        (MONTHLY, "Monthly"),
        (QUARTERLY, "Quarterly"),
        (YEARLY, "Yearly"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="finance_budgets"
    )
    name = models.CharField(max_length=120)
    account = models.ForeignKey(
        FinanceAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budgets",
    )
    option = models.ForeignKey(
        FinanceOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budgets",
    )
    period = models.CharField(
        max_length=16, choices=PERIOD_CHOICES, default=MONTHLY
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    starts_on = models.DateField(default=timezone.localdate)
    ends_on = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_budgets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-starts_on", "name")
        indexes = [models.Index(fields=["shop", "period"])]

    def __str__(self) -> str:
        return self.name


class FinanceChart(models.Model):
    """A saved graph. The X and Y axes are chosen separately."""

    LINE = "line"
    AREA = "area"
    BAR = "bar"
    DONUT = "donut"

    TYPE_CHOICES = (
        (LINE, "Line"),
        (AREA, "Area"),
        (BAR, "Bar"),
        (DONUT, "Donut"),
    )

    TIME = "time"
    PRODUCT = "product"
    CATEGORY = "category"
    OPTION = "option"
    ACCOUNT = "account"
    KIND = "kind"
    CUSTOM = "custom"

    X_CHOICES = (
        (TIME, "Time"),
        (PRODUCT, "Product"),
        (CATEGORY, "Product category"),
        (OPTION, "Finance option"),
        (ACCOUNT, "Account"),
        (KIND, "Entry kind"),
        (CUSTOM, "Values I type"),
    )

    AMOUNT = "amount"
    INCOME = "income"
    EXPENSE = "expense"
    NET = "net"
    TAX = "tax"
    DISCOUNT = "discount"
    PROFIT = "profit"
    LOSS = "loss"
    QUANTITY = "quantity"
    STOCK_AMOUNT = "stock_amount"
    STOCK_QUANTITY = "stock_quantity"
    STOCK_COST = "stock_cost"
    MARGIN = "margin"
    COUNT = "count"

    Y_CHOICES = (
        (AMOUNT, "Entry amount"),
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
        (NET, "Net (income less expense)"),
        (TAX, "Tax"),
        (DISCOUNT, "Discount"),
        (PROFIT, "Profit"),
        (LOSS, "Loss"),
        (QUANTITY, "Stock quantity moved"),
        (STOCK_AMOUNT, "Stock amount (selling value)"),
        (STOCK_QUANTITY, "Stock quantity in hand"),
        (STOCK_COST, "Stock cost (buying value)"),
        (MARGIN, "Stock margin"),
        (COUNT, "Number of entries"),
        (CUSTOM, "Values I type"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="finance_charts"
    )
    title = models.CharField(max_length=160)
    chart_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=BAR)
    x_source = models.CharField(max_length=16, choices=X_CHOICES, default=TIME)
    y_source = models.CharField(max_length=16, choices=Y_CHOICES, default=INCOME)
    x_values = models.JSONField(default=list, blank=True)
    y_values = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_charts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["shop", "-created_at"])]

    def __str__(self) -> str:
        return self.title


class FinanceReport(models.Model):
    """A report that was asked for, and the file it produced."""

    INCOME = "income"
    EXPENSES = "expenses"
    PROFIT_LOSS = "profit_loss"
    TAX = "tax"
    CASH_FLOW = "cash_flow"
    TRIAL_BALANCE = "trial_balance"
    BALANCE_SHEET = "balance_sheet"
    GENERAL_LEDGER = "general_ledger"
    BUDGETS = "budgets"

    KIND_CHOICES = (
        (INCOME, "Income"),
        (EXPENSES, "Expenses"),
        (PROFIT_LOSS, "Profit and loss"),
        (TAX, "Tax"),
        (CASH_FLOW, "Cash flow"),
        (TRIAL_BALANCE, "Trial balance"),
        (BALANCE_SHEET, "Balance sheet"),
        (GENERAL_LEDGER, "General ledger"),
        (BUDGETS, "Budgets"),
    )

    PDF = "pdf"
    XLSX = "xlsx"

    FORMAT_CHOICES = ((PDF, "PDF"), (XLSX, "Excel"))

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"

    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (RUNNING, "Running"),
        (READY, "Ready"),
        (FAILED, "Failed"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="finance_reports"
    )
    kind = models.CharField(
        max_length=24, choices=KIND_CHOICES, default=PROFIT_LOSS
    )
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default=PDF)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    content = models.BinaryField(blank=True, null=True)
    filename = models.CharField(max_length=200, blank=True)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    task_id = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["shop", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({self.get_format_display()})"

    @property
    def is_ready(self) -> bool:
        return self.status == self.READY and bool(self.content)

    @property
    def data(self) -> bytes:
        if not self.content:
            return b""
        return bytes(self.content)

    @property
    def content_type(self) -> str:
        if self.format == self.XLSX:
            return (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        return "application/pdf"


class Receipt(models.Model):
    """A receipt for a cart sale or purchase, kept as a PDF.

    The figures shown on the receipt are kept alongside the PDF so the print
    page never has to read them back from a record that may have moved on.
    """

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="receipts"
    )
    movement = models.ForeignKey(
        "smst_stocks.StockMovement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )
    reference = models.CharField(
        max_length=24, unique=True, default=generate_receipt_reference, editable=False
    )
    details = models.JSONField(default=dict, blank=True)
    content = models.BinaryField(blank=True, null=True)
    filename = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["shop", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.reference} — {self.details.get('product', 'Receipt')}"

    @property
    def data(self) -> bytes:
        if not self.content:
            return b""
        return bytes(self.content)
