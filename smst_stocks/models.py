"""Models for SmSt Stocks.

A shop owns products. Every change to a product's quantity is written as a
movement, so the ledger always explains the number on screen. Products can be
published and shared, which gives customers a page showing what is in stock and
a way to ask for it.
"""

import secrets

import cloudinary.uploader
from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db import transaction
from .validators import validate_attribute_length
from core.tasks import send_notification
def generate_token(length: int = 12) -> str:
    return secrets.token_hex(length)


class Shop(models.Model):
    """A shop. One account can run more than one."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stock_shops",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=200, blank=True)
    currency = models.CharField(max_length=8, default="Ksh")
    is_public = models.BooleanField(default=False)
    share_token = models.CharField(max_length=32, unique=True, default=generate_token)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = self.name.lower().replace(" ", "-")[:120] or "shop"
            slug = base
            counter = 2
            while Shop.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def share_url(self) -> str:
        return f"/smst_stocks/s/{self.share_token}/"

    @property
    def stock_value(self):
        from .services import shop_stock_value

        return shop_stock_value(self)

    @property
    def buying_value(self):
        from .services import shop_buying_value

        return shop_buying_value(self)


class Product(models.Model):
    """A stock item: a product, its price and how many are in hand."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180)
    sku = models.CharField(max_length=60, blank=True)
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True, validators=[validate_attribute_length])
    image = CloudinaryField("smst_stocks/product", blank=True, null=True)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit = models.CharField(max_length=24, default="piece")
    category = models.CharField(max_length=80, blank=True)
    is_published = models.BooleanField(default=False)
    share_token = models.CharField(max_length=32, unique=True, default=generate_token)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        unique_together = ("shop", "slug")
        indexes = [
            models.Index(fields=["shop", "name"]),
            models.Index(fields=["is_published"]),
        ]

    def __str__(self) -> str:
        return self.name

    @transaction.atomic
    def save(self, *args, **kwargs):
        is_created = self._state.adding
        if not self.slug:
            base = self.name.lower().replace(" ", "-")[:150] or "product"
            slug = base
            counter = 2
            while (
                Product.objects.filter(shop=self.shop, slug=slug)
                .exclude(pk=self.pk)
                .exists()
            ):
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        old_image = None

        if self.pk:
            old_instance = type(self).objects.filter(pk=self.pk).first()
            if old_instance and old_instance.image:
                old_image = old_instance.image.public_id
        super().save(*args, **kwargs)
        new_image = self.image.public_id if self.image else None
        if new_image != old_image and new_image and old_image:
            cloudinary.uploader.destroy(
                old_image,
                invalidate=True
            )
        text = ['CHANGE PRODUCT','edited']
        if is_created:
            text = ['NEW PRODUCT','created']
        send_notification.delay(self.shop.owner.username, f'{text[0]}: Product {self.name} {text[1]}', f'Buying: {self.buying_price}, Selling: {self.selling_price}, Stock Amount: {int(self.quantity)}', url=f"https://app.smst.africa/smst_stocks/products/{self.id}", pro=self.shop.owner.has_active_subscription)
    # ---------------------------------------------------------------- state
    @property
    def stock_state(self) -> str:
        """out, low or in_stock."""
        if self.quantity <= 0:
            return "out"
        if self.reorder_level and self.quantity <= self.reorder_level:
            return "low"
        return "in_stock"

    @property
    def is_available(self) -> bool:
        return self.quantity > 0

    @property
    def margin(self):
        if not self.selling_price:
            return 0
        return ((self.selling_price - self.buying_price) / self.selling_price) * 100

    @property
    def margin_value(self):
        return self.selling_price - self.buying_price

    @property
    def stock_value(self):
        return self.quantity * self.selling_price

    @property
    def suggested_order(self):
        """How much to ask the supplier for to bring the shelf back up."""
        target = self.reorder_level * 2
        if target <= self.quantity:
            return 0
        return target - self.quantity

    @property
    def order_cost(self):
        return self.suggested_order * self.buying_price

    @property
    def share_url(self) -> str:
        return f"/smst_stocks/p/{self.share_token}/"

    @property
    def cart_quantity(self):
        """How much of this item is being held in someone's cart."""
        return self.cart_lines.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def is_in_cart(self) -> bool:
        return self.cart_quantity > 0

    def attribute_lines(self):
        return [
            (key, value)
            for key, value in (self.attributes or {}).items()
            if str(value).strip()
        ]


class StockMovement(models.Model):
    """One line of the ledger. Every change to a quantity is recorded here."""

    SALE = "sale"
    DELIVERY = "delivery"
    OPENING = "opening"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    LOSS = "loss"

    KIND_CHOICES = (
        (SALE, "Sale"),
        (DELIVERY, "Delivery"),
        (OPENING, "Opening stock"),
        (ADJUSTMENT, "Adjustment"),
        (RETURN, "Customer return"),
        (LOSS, "Loss or damage"),
    )

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="movements"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=ADJUSTMENT)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Positive adds to stock, negative takes from it.",
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    note = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["product", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.quantity} — {self.product.name}"

from django.utils.translation import gettext as _

class Order(models.Model):
    """A request for stock from a customer using a shared link."""

    PENDING = _("pending")
    CONFIRMED = _("confirmed")
    FULFILLED = _("fulfilled")
    CANCELLED = _("cancelled")

    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (CONFIRMED, "Confirmed"),
        (FULFILLED, "Fulfilled"),
        (CANCELLED, "Cancelled"),
    )

    reference = models.CharField(max_length=16, unique=True, editable=False)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="orders")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="orders"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=40)
    customer_email = models.EmailField(blank=True)
    note = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["shop", "status"])]

    def __str__(self) -> str:
        return f"{self.reference} — {self.product.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"SS-{secrets.token_hex(4).upper()}"
        super().save(*args, **kwargs)

    @property
    def total(self):
        return self.quantity * self.product.selling_price


class CartLine(models.Model):
    """Stock a person is holding in their cart until it is processed.

    Adding to the cart takes the quantity off the shelf so it cannot be traded
    twice, and marks the line buy or sell. Processing writes the matching
    movement and finance entry; releasing the line puts the stock back as it
    was. A person can hold both a buy and a sell of the same item, so the line
    is keyed by direction as well.
    """

    BUY = "buy"
    SELL = "sell"

    DIRECTION_CHOICES = ((BUY, "Buying"), (SELL, "Selling"))

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="cart_lines"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stock_cart_lines",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    direction = models.CharField(
        max_length=8, choices=DIRECTION_CHOICES, default=SELL
    )
    #: The finance account the money settles through, and the finance options
    #: applied on top. They are kept as plain ids so the stock app never holds
    #: a foreign key into SmSt Finances.
    account_id = models.PositiveBigIntegerField(null=True, blank=True)
    option_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        unique_together = ("user", "product", "direction")
        indexes = [models.Index(fields=["user", "direction"])]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} {self.quantity} — {self.product.name}"

    @property
    def is_sell(self) -> bool:
        return self.direction == self.SELL

    @property
    def shop(self):
        return self.product.shop

    @property
    def unit_price(self):
        """A sell line reads the selling price, a buy line the buying price."""
        return self.product.selling_price if self.is_sell else self.product.buying_price

    @property
    def total(self):
        return self.quantity * self.unit_price


class ShareLink(models.Model):
    """A link that expires, or that can be switched off without changing the product."""

    token = models.CharField(max_length=40, unique=True, default=generate_token)
    shop = models.ForeignKey(
        Shop, on_delete=models.CASCADE, related_name="share_links"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="share_links",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.token} ({self.product or self.shop})"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_open(self) -> bool:
        return self.is_active and not self.is_expired

    def target_path(self) -> str:
        if self.product:
            return f"/smst_stocks/p/{self.product.share_token}/"
        return f"/smst_stocks/s/{self.shop.share_token}/"


class ReportRun(models.Model):
    """A report that was asked for, and the file it produced."""

    STOCK = "stock"
    MOVEMENTS = "movements"
    LOW_STOCK = "low_stock"
    ORDERS = "orders"

    KIND_CHOICES = (
        (STOCK, "Stock valuation"),
        (MOVEMENTS, "Movements"),
        (LOW_STOCK, "Items to reorder"),
        (ORDERS, "Orders"),
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

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="reports")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=STOCK)
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default=PDF)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    #: The file itself. It is kept with the report so that the app does not
    #: need a media folder to serve it.
    content = models.BinaryField(blank=True, null=True)
    filename = models.CharField(max_length=200, blank=True)
    task_id = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({self.get_format_display()})"

    @property
    def is_ready(self) -> bool:
        return self.status == self.READY and bool(self.content)

    @property
    def data(self) -> bytes:
        """The file, as bytes."""
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
