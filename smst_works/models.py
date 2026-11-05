"""Models for SmSt Works.

The app runs the people side of a shop: who works there, what their rank lets
them do, the customers who earn loyalty points, the suppliers kept for quick
reference, the guides everyone can read, and the jobs that move stock from one
shape to another on a live timeline.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

#: The kinds of permission a rank can hold.
VIEW = "view"
ACTION = "action"
ACTIVITY = "activity"
PERMISSION_KINDS = (
    (VIEW, "Views"),
    (ACTION, "Actions"),
    (ACTIVITY, "Activities"),
)

#: The things a rank can allow. An owner always has all of them.
PERMISSIONS = (
    # Views: the links and pages a rank may open.
    ("works.view.dashboard", "Open the shop floor", VIEW),
    ("works.view.jobs", "Open jobs", VIEW),
    ("works.view.employees", "Open employees", VIEW),
    ("works.view.ranks", "Open ranks", VIEW),
    ("works.view.customers", "Open loyalty customers", VIEW),
    ("works.view.suppliers", "Open suppliers", VIEW),
    ("works.view.guides", "Open guides", VIEW),
    ("stocks.view", "Open the stock dashboard", VIEW),
    ("stocks.view.products", "Open items", VIEW),
    ("stocks.view.movements", "Open the stock ledger", VIEW),
    ("stocks.view.low_stock", "Open items to reorder", VIEW),
    ("stocks.view.orders", "Open orders", VIEW),
    ("stocks.view.reports", "Open stock reports", VIEW),
    ("stocks.view.links", "Open shared links", VIEW),
    ("stocks.view.shops", "Open shop settings", VIEW),
    ("finances.view.dashboard", "Open the finance dashboard", VIEW),
    ("finances.view.statements", "Open statements", VIEW),
    ("finances.view.reports", "Open finance reports", VIEW),
    ("finances.view.entries", "Open finance entries", VIEW),
    ("finances.view.options", "Open finance options", VIEW),
    ("finances.view.accounts", "Open finance accounts", VIEW),
    ("finances.view.charts", "Open finance graphs", VIEW),
    ("finances.view.budgets", "Open budgets", VIEW),
    # Actions: the things a rank may change or produce.
    ("stocks.add", "Add stock", ACTION),
    ("stocks.move", "Move stock", ACTION),
    ("stocks.reports.download", "Download stock reports", ACTION),
    ("finances.manage", "Manage the books", ACTION),
    ("finances.graphs.generate", "Generate finance graphs", ACTION),
    ("finances.reports.download", "Download finance reports", ACTION),
    ("customers.manage", "Manage loyalty customers", ACTION),
    ("suppliers.manage", "Manage suppliers", ACTION),
    ("jobs.create", "Create jobs", ACTION),
    ("jobs.run", "Start and finish jobs", ACTION),
    ("guides.manage", "Write guides", ACTION),
    ("employees.manage", "Hire and edit employees", ACTION),
    ("ranks.manage", "Set ranks and permissions", ACTION),
    # Activities: which rows a rank may see.
    ("stocks.ledger.all", "See every stock entry", ACTIVITY),
    ("stocks.ledger.buy", "See stock coming in", ACTIVITY),
    ("stocks.ledger.sell", "See stock going out", ACTIVITY),
    ("finances.entries.all", "See every finance entry", ACTIVITY),
)
ALL_PERMISSIONS = tuple(key for key, _label, _kind in PERMISSIONS)
PERMISSION_LABELS = {
    key: label for key, label, _kind in PERMISSIONS
}
PERMISSION_GROUPS = tuple(
    (
        label,
        tuple(
            (key, permission_label)
            for key, permission_label, kind in PERMISSIONS
            if kind == kind_key
        ),
    )
    for kind_key, label in PERMISSION_KINDS
)

#: Ranks every shop starts with. The owner can change them at any time.
DEFAULT_RANKS = (
    ("Manager", ALL_PERMISSIONS, "Runs the shop day to day."),
    (
        "Accountant",
        (
            "works.view.dashboard",
            "works.view.jobs",
            "works.view.customers",
            "works.view.suppliers",
            "works.view.guides",
            "stocks.view",
            "stocks.view.products",
            "stocks.view.movements",
            "stocks.view.low_stock",
            "stocks.view.orders",
            "stocks.view.reports",
            "stocks.ledger.all",
            "stocks.reports.download",
            "finances.view.dashboard",
            "finances.view.statements",
            "finances.view.reports",
            "finances.view.entries",
            "finances.view.options",
            "finances.view.accounts",
            "finances.view.charts",
            "finances.view.budgets",
            "finances.entries.all",
            "finances.manage",
            "finances.graphs.generate",
            "finances.reports.download",
            "customers.manage",
            "suppliers.manage",
            "jobs.create",
            "jobs.run",
        ),
        "Keeps the books and the customer list; does not move stock.",
    ),
    (
        "Cleaner",
        (
            "works.view.dashboard",
            "works.view.jobs",
            "works.view.guides",
            "stocks.view",
            "stocks.view.products",
            "stocks.view.movements",
            "stocks.view.low_stock",
            "stocks.view.orders",
            "stocks.move",
            "finances.view.entries",
            "jobs.create",
            "jobs.run",
        ),
        "Can use stock and run jobs; cannot add stock or see every entry.",
    ),
)


def generate_token(length: int = 6) -> str:
    return secrets.token_hex(length).upper()


class Rank(models.Model):
    """A job title with a list of permissions attached."""

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="ranks"
    )
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=240, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("shop", "name")

    def __str__(self) -> str:
        return self.name

    def has(self, permission: str) -> bool:
        return permission in (self.permissions or [])

    @property
    def permission_labels(self):
        return [
            PERMISSION_LABELS.get(key, key) for key in (self.permissions or [])
        ]

    @property
    def permission_items(self):
        return [
            (key, PERMISSION_LABELS.get(key, key))
            for key in (self.permissions or [])
        ]


class Employee(models.Model):
    """Someone who works at the shop. A login is linked when the email matches."""

    HIRED = "hired"
    SUSPENDED = "suspended"
    LEFT = "left"

    STATUS_CHOICES = (
        (HIRED, "On the team"),
        (SUSPENDED, "Suspended"),
        (LEFT, "Left"),
    )

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="employees"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_employments",
    )
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=80, blank=True)
    rank = models.ForeignKey(
        Rank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=HIRED
    )
    hired_at = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("shop", "user")

    def __str__(self) -> str:
        return self.name

    @property
    def permissions(self):
        return frozenset((self.rank.permissions if self.rank else []) or [])

    def can(self, permission: str) -> bool:
        return bool(self.rank and self.rank.has(permission))


class Customer(models.Model):
    """A loyalty customer of the shop."""

    shop = models.ForeignKey(
        "smst_stocks.Shop",
        on_delete=models.CASCADE,
        related_name="loyalty_customers",
    )
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def tier(self) -> str:
        if self.points >= 500:
            return "gold"
        if self.points >= 200:
            return "silver"
        return "bronze"


class LoyaltyTransaction(models.Model):
    """One change to a customer's points, kept for the record."""

    EARN = "earn"
    REDEEM = "redeem"
    ADJUST = "adjust"

    KIND_CHOICES = (
        (EARN, "Earned"),
        (REDEEM, "Redeemed"),
        (ADJUST, "Adjusted"),
    )

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="loyalty_transactions"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=ADJUST)
    points = models.IntegerField(help_text="Positive adds, negative takes away.")
    reason = models.CharField(max_length=160, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_actions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.customer} {self.points:+d}"


class Supplier(models.Model):
    """A supplier kept for quick reference, linked to the items they bring."""

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField(max_length=120)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    products = models.ManyToManyField(
        "smst_stocks.Product", blank=True, related_name="suppliers"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Guide(models.Model):
    """A rule or how-to the team can read at any time."""

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="guides"
    )
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=80, blank=True)
    body = models.TextField()
    is_published = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guides_written",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "title")

    def __str__(self) -> str:
        return self.title


class Job(models.Model):
    """A piece of work on the shop floor, drawn on the live timeline."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (RUNNING, "Running"),
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
    )

    OPEN_STATUSES = (PENDING, RUNNING)

    shop = models.ForeignKey(
        "smst_stocks.Shop", on_delete=models.CASCADE, related_name="jobs"
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=PENDING
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs_created",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def waiting_seconds(self) -> float:
        if self.status != self.PENDING:
            return 0.0
        return max(0.0, (timezone.now() - self.created_at).total_seconds())

    @property
    def elapsed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or timezone.now()
        return max(0.0, (end - self.started_at).total_seconds())

    @property
    def duration_seconds(self):
        if self.started_at and self.finished_at:
            return max(0.0, (self.finished_at - self.started_at).total_seconds())
        return None

    def start(self):
        self.status = self.RUNNING
        self.started_at = self.started_at or timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])

    def finish(self, success: bool = True, note: str = ""):
        self.status = self.SUCCEEDED if success else self.FAILED
        self.started_at = self.started_at or timezone.now()
        self.finished_at = timezone.now()
        self.note = note or ""
        self.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "note",
                "updated_at",
            ]
        )


class JobInput(models.Model):
    """A stock product a job takes in."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="inputs")
    product = models.ForeignKey(
        "smst_stocks.Product",
        on_delete=models.CASCADE,
        related_name="job_inputs",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.quantity:g} {self.product.unit} {self.product.name}"

    @property
    def unit(self) -> str:
        return self.product.unit


class JobOutput(models.Model):
    """A stock product a job produces."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="outputs")
    product = models.ForeignKey(
        "smst_stocks.Product",
        on_delete=models.CASCADE,
        related_name="job_outputs",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.quantity:g} {self.product.unit} {self.product.name}"

    @property
    def unit(self) -> str:
        return self.product.unit
