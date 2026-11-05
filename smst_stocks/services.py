"""The rules of SmSt Stocks.

Everything that changes a quantity, a price or a stock total goes through this
module, so the ledger, the dashboard and the shared pages can never disagree.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from core.tasks import send_notification

from .models import CartLine, Order, Product, ShareLink, Shop, StockMovement
from . import finance_bridge
from .realtime import broadcast_product, broadcast_shop

logger = logging.getLogger("smst")

ZERO = Decimal("0")


class StockError(Exception):
    """A rule was broken. The message is safe to show the user."""


# --------------------------------------------------------------------- plans
def plan_limits(user) -> dict:
    """The limits that come with the user's plan.

    Free accounts carry one shop and 50 items. SmSt Pro lifts both.
    """
    pro = False
    if user is not None and getattr(user, "is_authenticated", False):
        pro = bool(getattr(user, "has_active_subscription", False))

    if pro:
        return {"plan": "pro", "shops": None, "items_per_shop": 2000}
    return {"plan": "free", "shops": 1, "items_per_shop": 50}


def check_shop_limit(user) -> None:
    limits = plan_limits(user)
    if limits["shops"] is None:
        return
    owned = Shop.objects.filter(owner=user).count()
    if owned >= limits["shops"]:
        raise StockError(
            "The free plan carries one shop. Join SmSt Pro to run more than one."
        )


def check_item_limit(shop) -> None:
    limits = plan_limits(shop.owner)
    limit = limits["items_per_shop"]
    if limit is None:
        return
    count = Product.objects.filter(shop=shop).count()
    if count >= limit:
        raise StockError(
            f"This shop already holds {limit} items. Join SmSt Pro to add more."
        )


# ------------------------------------------------------------------ money
def shop_stock_value(shop) -> Decimal:
    total = Product.objects.filter(shop=shop).aggregate(
        total=Sum(F("quantity") * F("selling_price"))
    )
    return total["total"] or ZERO


def shop_buying_value(shop) -> Decimal:
    total = Product.objects.filter(shop=shop).aggregate(
        total=Sum(F("quantity") * F("buying_price"))
    )
    return total["total"] or ZERO


def shop_margin_value(shop) -> Decimal:
    return shop_stock_value(shop) - shop_buying_value(shop)


def low_stock_products(shop):
    return list(
        Product.objects.filter(shop=shop)
        .filter(Q(quantity__lte=0) | Q(reorder_level__gt=0, quantity__lte=F("reorder_level")))
        .order_by("quantity", "name")
    )


def shop_summary(shop) -> dict:
    products = Product.objects.filter(shop=shop)
    counts = products.aggregate(total=Sum("quantity"))
    low = low_stock_products(shop)
    pending_orders = Order.objects.filter(shop=shop, status=Order.PENDING).count()
    return {
        "products": products.count(),
        "units": counts["total"] or ZERO,
        "stock_value": shop_stock_value(shop),
        "buying_value": shop_buying_value(shop),
        "margin_value": shop_margin_value(shop),
        "low_stock": low,
        "low_stock_count": len(low),
        "out_of_stock": len([p for p in low if p.quantity <= 0]),
        "pending_orders": pending_orders,
        "published": products.filter(is_published=True).count(),
    }


def summary_payload(shop) -> dict:
    """The shop's totals in a form that can travel over a websocket."""
    summary = shop_summary(shop)
    return {
        "products": summary["products"],
        "units": float(summary["units"]),
        "stock_value": float(summary["stock_value"]),
        "buying_value": float(summary["buying_value"]),
        "margin_value": float(summary["margin_value"]),
        "low_stock_count": summary["low_stock_count"],
        "out_of_stock": summary["out_of_stock"],
        "pending_orders": summary["pending_orders"],
    }


# --------------------------------------------------------------- movements
#: Movements that take stock away from the shelf.
OUTGOING_KINDS = {StockMovement.SALE, StockMovement.LOSS}


def apply_kind_sign(kind: str, quantity) -> Decimal:
    """Turn a number the shopkeeper typed into a signed movement.

    A sale of 3 becomes -3. A delivery of 20 becomes +20. An adjustment keeps
    the sign it was given, because that is the point of an adjustment.
    """
    try:
        amount = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError):
        raise ValueError("Enter how many items moved.")

    if kind in OUTGOING_KINDS:
        amount = -abs(amount)
    elif kind != StockMovement.ADJUSTMENT:
        amount = abs(amount)

    return amount


def _sync_finance(movement, account=None, user=None):
    """Post the movement to SmSt Finances without risking the stock write.

    The two apps share one book, but a missing finance install or a bad account
    must never stop a delivery or a sale being recorded. A failure here is
    logged and the stock movement goes through.
    """
    try:
        finance = finance_bridge.services()
    except Exception:  # noqa: BLE001 - finances may not be installed
        return None
    try:
        return finance.sync_stock_movement(movement, account=account, user=user)
    except Exception:  # noqa: BLE001 - never lose the stock movement
        logger.warning(
            "Could not post stock movement %s to finances", movement.pk, exc_info=True
        )
        return None


@transaction.atomic
def record_movement(
    product: Product,
    kind: str,
    quantity,
    note: str = "",
    unit_cost=None,
    user=None,
    broadcast: bool = True,
    account=None,
):
    """Write a ledger line and move the quantity to match.

    The number the shopkeeper typed is turned into a signed movement: a sale
    of 3 takes 3 off the shelf, a delivery of 20 puts 20 on it. An adjustment
    keeps the sign it was given, because that is the point of an adjustment. A
    sale that would take the count below zero is refused.

    ``account`` is the finance account the money moved through, chosen on the
    movement form. When it is given the movement is posted into SmSt Finances
    in the same breath; a loss is always posted, because the value leaves
    stock whether cash moves or not.
    """
    quantity = apply_kind_sign(kind, quantity)
    if quantity == 0:
        raise StockError("A movement of zero changes nothing.")

    if kind == StockMovement.SALE and product.quantity + quantity < 0:
        raise StockError(
            f"There are only {product.quantity:g} {product.unit} of {product.name} in hand."
        )

    movement = StockMovement.objects.create(
        product=product,
        kind=kind,
        quantity=quantity,
        note=note or "",
        unit_cost=unit_cost,
        created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
    )
    stock_level_before = product.quantity
    Product.objects.filter(pk=product.pk).update(
        quantity=F("quantity") + quantity, updated_at=timezone.now()
    )
    product.refresh_from_db(fields=["quantity", "updated_at"])
    stock_level_after = product.quantity
    
    if stock_level_after != stock_level_before and stock_level_after > Decimal('0'):
        send_notification.delay(user.username, f'STOCK CHANGE: Product {product.name} has moved', f"Was {int(stock_level_before)} - Now {int(stock_level_after)} {product.unit}(s) left.", url=f'https://app.smst.africa/smst_stocks/products/{product.id}/')
    
    if account not in (None, "") or kind == StockMovement.LOSS:
        _sync_finance(movement, account=account, user=user)

    if broadcast:
        broadcast_product(
            product,
            event="product.moved",
            extra={
                "movement_id": movement.id,
                "kind": kind,
                "summary": summary_payload(product.shop),
            },
        )

    
    if product.quantity == Decimal('0'):
        send_notification.delay(user.username, f'OUT OF STOCK: Product {product.name} has reached 0 stocks', 'If you have the permissions press here to reorder.', url=f'https://app.smst.africa/smst_stocks/products/{product.id}/')
    return movement


@transaction.atomic
def record_delivery(shop, lines, note: str = "", unit_cost=None, user=None, account=None):
    """Record a delivery with several lines at once."""
    if not lines:
        raise StockError("A delivery needs at least one item.")

    movements = []
    for line in lines:
        product = Product.objects.select_for_update().filter(
            pk=line.get("product"), shop=shop
        ).first()
        if not product:
            raise StockError("One of the items in this delivery is not in your shop.")
        movements.append(
            record_movement(
                product,
                StockMovement.DELIVERY,
                line.get("quantity", 0),
                note=note,
                unit_cost=line.get("unit_cost", unit_cost),
                user=user,
                broadcast=False,
                account=account,
            )
        )

    for movement in movements:
        broadcast_product(
            movement.product,
            event="product.moved",
            extra={"movement_id": movement.id, "kind": movement.kind},
        )

    return movements


# -------------------------------------------------------------------- cart
#: The ledger line a processed cart line writes.
CART_MOVEMENT_KIND = {
    CartLine.SELL: StockMovement.SALE,
    CartLine.BUY: StockMovement.DELIVERY,
}

#: How a finance option's kind reads once it lands in the books.
CART_OPTION_KIND = {
    "tax": "tax",
    "discount": "discount",
    "expense": "expense",
    "income": "income",
    "fee": "expense",
    "refund": "refund",
    "other": "adjustment",
}


def cart_lines(user, shop=None):
    """The lines the person is holding, newest first."""
    lines = CartLine.objects.filter(user=user).select_related(
        "product", "product__shop"
    )
    if shop is not None:
        lines = lines.filter(product__shop=shop)
    return lines


def product_holders(product):
    """Who is holding this item in a cart, and how much."""
    return product.cart_lines.select_related("user").order_by("-updated_at")


def cart_totals(lines) -> dict:
    """What the cart is worth, split by direction."""
    lines = list(lines)
    sell = sum((line.total for line in lines if line.is_sell), ZERO)
    buy = sum((line.total for line in lines if not line.is_sell), ZERO)
    return {"count": len(lines), "sell_total": sell, "buy_total": buy}


def _clean_quantity(quantity) -> Decimal:
    try:
        amount = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError):
        raise StockError("Enter how many to hold.")
    if amount <= 0:
        raise StockError("Choose how many to hold.")
    return amount


def _clean_option_ids(option_ids):
    if not option_ids:
        return []
    return [int(getattr(option, "pk", option)) for option in option_ids]


@transaction.atomic
def add_to_cart(user, product, quantity, direction, account=None, option_ids=None):
    """Hold a product in the cart, taking it off the shelf as it goes in.

    The quantity leaves what is in hand so the same stock cannot be traded
    twice. A line the person already holds for the same item and direction
    simply grows; a buy and a sell of the same item stay apart.
    """
    if direction not in {choice[0] for choice in CartLine.DIRECTION_CHOICES}:
        raise StockError("A cart line is either a buy or a sell.")
    amount = _clean_quantity(quantity)

    locked = Product.objects.select_for_update().get(pk=product.pk)
    # A buy may go past zero: the stock is only there because it was just bought.
    if direction == CartLine.SELL and locked.quantity < amount:
        raise StockError(
            f"There are only {locked.quantity:g} {locked.unit} of {locked.name} in hand."
        )

    line = (
        CartLine.objects.select_for_update()
        .filter(user=user, product=locked, direction=direction)
        .first()
    )
    if line:
        line.quantity = line.quantity + amount
    else:
        line = CartLine(user=user, product=locked, direction=direction, quantity=amount)
    if account not in (None, ""):
        line.account_id = getattr(account, "pk", account)
    if option_ids is not None:
        line.option_ids = _clean_option_ids(option_ids)
    line.save()

    Product.objects.filter(pk=locked.pk).update(
        quantity=F("quantity") - amount, updated_at=timezone.now()
    )
    locked.refresh_from_db(fields=["quantity", "updated_at"])
    broadcast_product(locked, event="product.moved", extra={"cart": "added"})
    return line


@transaction.atomic
def release_cart_line(user, line):
    """Let a line go, putting its stock back on the shelf untouched."""
    line = (
        CartLine.objects.select_for_update().filter(pk=line.pk, user=user).first()
    )
    if line is None:
        raise StockError("That line is not in your cart.")

    locked = Product.objects.select_for_update().get(pk=line.product_id)
    quantity = line.quantity
    Product.objects.filter(pk=locked.pk).update(
        quantity=F("quantity") + quantity, updated_at=timezone.now()
    )
    line.delete()
    locked.refresh_from_db(fields=["quantity", "updated_at"])
    broadcast_product(locked, event="product.moved", extra={"cart": "released"})
    return locked


def _post_cart_options(user, product, movement, option_ids):
    """Post the finance options chosen for a processed line.

    A bad option must never lose the stock movement, so each one is posted on
    its own and a failure is only logged.
    """
    if not option_ids:
        return
    try:
        finance_models = finance_bridge.models()
        finance = finance_bridge.services()
    except Exception:  # noqa: BLE001 - finances may not be installed
        return

    base = abs(movement.quantity) * (
        product.selling_price if movement.kind == StockMovement.SALE else product.buying_price
    )
    for option in finance_models.FinanceOption.objects.filter(
        shop=product.shop, pk__in=option_ids, is_active=True
    ):
        try:
            finance.create_entry(
                product.shop,
                {
                    "option": option,
                    "movement": movement,
                    "product": product,
                    "kind": CART_OPTION_KIND.get(option.kind, "adjustment"),
                    "base_amount": base,
                    "amount": option.amount_for(base),
                    "description": option.name,
                    "occurred_at": movement.created_at,
                },
                user=user,
            )
        except Exception:  # noqa: BLE001 - never lose the stock movement
            logger.warning(
                "Could not post cart option %s for movement %s",
                option.pk,
                movement.pk,
                exc_info=True,
            )


def process_cart(user, shop, account=None, option_ids=None):
    """Finish every line in the cart with one set of finances.

    Each line keeps its own movement, receipt and books entry. A line that
    cannot go through stays where it is and is reported, so the rest of the
    trade is never lost with it.
    """
    done, failed = [], []
    for line in list(cart_lines(user, shop)):
        try:
            done.append(
                (
                    line,
                    process_cart_line(
                        user, line, account=account, option_ids=option_ids
                    ),
                )
            )
        except StockError as error:
            failed.append((line.product.name, str(error)))
    return done, failed


@transaction.atomic
def process_cart_line(user, line, account=None, option_ids=None):
    """Finish a cart line: write the movement and the finance entries.

    The stock already left the shelf when it went into the cart, so it is put
    back first and the movement below records the whole change rather than
    half of it.
    """
    line = (
        CartLine.objects.select_for_update().filter(pk=line.pk, user=user).first()
    )
    if line is None:
        raise StockError("That line is not in your cart.")

    locked = Product.objects.select_for_update().get(pk=line.product_id)
    quantity = line.quantity
    Product.objects.filter(pk=locked.pk).update(
        quantity=F("quantity") + quantity, updated_at=timezone.now()
    )
    locked.refresh_from_db(fields=["quantity"])

    if account in (None, ""):
        account = line.account_id
    choices = option_ids if option_ids is not None else line.option_ids

    movement = record_movement(
        locked,
        CART_MOVEMENT_KIND[line.direction],
        quantity,
        note=f"From the cart ({line.get_direction_display().lower()})",
        unit_cost=locked.buying_price,
        user=user,
        account=account,
    )
    _post_cart_options(user, locked, movement, choices)
    line.delete()
    return movement


# ------------------------------------------------------------------ orders
@transaction.atomic
def create_order(
    product: Product,
    quantity,
    customer_name: str,
    customer_phone: str,
    customer_email: str = "",
    note: str = "",
):
    """Take a request for stock from a customer and hold the stock for it.

    The stock is taken off the shelf straight away so that the same item
    cannot be promised twice. Cancelling the order puts it back.
    """
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise StockError("Choose how many you need.")

    locked = Product.objects.select_for_update().get(pk=product.pk)
    if locked.quantity < quantity:
        available = locked.quantity
        raise StockError(
            f"There are only {available:g} {locked.unit} of {locked.name} in hand right now."
        )

    order = Order.objects.create(
        shop=locked.shop,
        product=locked,
        quantity=quantity,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email or "",
        note=note or "",
    )

    record_movement(
        locked,
        StockMovement.SALE,
        -quantity,
        note=f"Order {order.reference}",
        user=locked.shop.owner,
        broadcast=False,    
    )

    broadcast_product(
        locked,
        event="product.moved",
        extra={"movement_kind": StockMovement.SALE, "order": order.reference},
    )
    broadcast_shop(
        locked.shop,
        "order.created",
        {
            "reference": order.reference,
            "product": locked.name,
            "quantity": float(quantity),
            "customer_name": customer_name,
        },
    )

    return order


@transaction.atomic
def cancel_order(order: Order):
    """Cancel an order and put the stock back on the shelf."""
    if order.status == Order.CANCELLED:
        return order
    if order.status == Order.FULFILLED:
        raise StockError("A fulfilled order cannot be cancelled.")

    record_movement(
        order.product,
        StockMovement.RETURN,
        order.quantity,
        note=f"Order {order.reference} cancelled",
        user=order.shop.owner,
        broadcast=False,
    )
    order.status = Order.CANCELLED
    order.save(update_fields=["status", "updated_at"])

    broadcast_product(
        order.product,
        event="product.moved",
        extra={"movement_kind": StockMovement.RETURN, "order": order.reference},
    )
    return order


@transaction.atomic
def update_order_status(order: Order, status: str):
    valid = {choice[0] for choice in Order.STATUS_CHOICES}
    if status not in valid:
        raise StockError("That is not a status an order can hold.")
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    broadcast_shop(
        order.shop,
        "order.updated",
        {"reference": order.reference, "status": status},
    )
    return order


# ------------------------------------------------------------------- links
def create_share_link(shop, product=None, expires_at=None) -> ShareLink:
    return ShareLink.objects.create(
        shop=shop, product=product, expires_at=expires_at
    )


def resolve_share_link(token: str):
    """Find an open share link, counting the visit."""
    link = (
        ShareLink.objects.select_related("shop", "product")
        .filter(token=token)
        .first()
    )
    if not link or not link.is_open:
        return None
    ShareLink.objects.filter(pk=link.pk).update(views=link.views + 1)
    return link
