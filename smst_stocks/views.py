"""The SmSt Stocks app.

The pages are thin. They set up the shop, hand the work to the API and let the
browser keep the numbers live over a websocket.
"""

import logging
from functools import wraps
from json import dumps

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import finance_bridge
from .models import CartLine, Order, Product, ReportRun, ShareLink, Shop, StockMovement
from .services import (
    StockError,
    add_to_cart,
    cart_lines,
    cart_totals,
    plan_limits,
    process_cart,
    process_cart_line,
    product_holders,
    release_cart_line,
    shop_summary,
)

logger = logging.getLogger("smst")

LOGIN_URL = "https://user.smst.africa/"

REPORT_KINDS = [
    (ReportRun.STOCK, "Stock valuation", "Every item, what it cost and what it is worth now."),
    (ReportRun.MOVEMENTS, "Movements", "The ledger of everything that came in and went out."),
    (ReportRun.LOW_STOCK, "Items to reorder", "What is running low, and how much to order."),
    (ReportRun.ORDERS, "Orders", "Every request a customer has sent through a shared link."),
]


def _shops_for(user):
    """Every shop the user owns or works at."""
    if not user.is_authenticated:
        return Shop.objects.none()
    try:
        from smst_works.services import shops_for

        return shops_for(user)
    except Exception:  # noqa: BLE001 - works may not be installed or migrated
        logger.warning(
            "Could not read the work team; falling back to owned shops",
            exc_info=True,
        )
        return Shop.objects.filter(owner=user)


def _shop_for(user, request):
    """The shop this request is about. The first one unless another is asked for."""
    if not user.is_authenticated:
        return None
    shop_id = request.GET.get("shop") or request.POST.get("shop")
    queryset = _shops_for(user)
    if shop_id:
        shop = queryset.filter(pk=shop_id).first()
        if shop:
            return shop
    return queryset.order_by("name").first()


def _permissions(shop, user):
    if not shop or not user or not user.is_authenticated:
        return set()
    if shop.owner_id == user.id:
        try:
            from smst_works.models import ALL_PERMISSIONS

            return set(ALL_PERMISSIONS)
        except Exception:  # noqa: BLE001 - works may not be installed
            return set()
    try:
        from smst_works.services import permissions_for

        return set(permissions_for(shop, user))
    except Exception:  # noqa: BLE001 - works may not be migrated
        return set()


def _can(shop, user, permission):
    if shop and user and shop.owner_id == user.id:
        return True
    try:
        from smst_works.services import has_permission

        return has_permission(shop, user, permission)
    except Exception:  # noqa: BLE001 - works may not be migrated
        return False


def _requires(permission):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            shop = _shop_for(request.user, request)
            if shop and not _can(shop, request.user, permission):
                raise PermissionDenied(
                    f"Your rank does not allow that. It needs the “{permission}” permission."
                )
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def _visible_movements(queryset, shop, user):
    """The rows a person may see: all of them, or only their own and their kinds."""
    permissions = _permissions(shop, user)
    if "stocks.ledger.all" in permissions:
        return queryset
    queryset = queryset.filter(created_by=user)
    kinds = set()
    if "stocks.ledger.buy" in permissions or "stocks.add" in permissions:
        kinds |= {StockMovement.DELIVERY, StockMovement.OPENING}
    if "stocks.ledger.sell" in permissions or "stocks.move" in permissions:
        kinds |= {
            StockMovement.SALE,
            StockMovement.ADJUSTMENT,
            StockMovement.RETURN,
            StockMovement.LOSS,
        }
    return queryset.filter(kind__in=kinds) if kinds else queryset.none()


def _finance_accounts(shop):
    """The accounts a movement can save its money in, cash first.

    SmSt Finances owns the chart of accounts. The import stays inside the
    function so the stock app keeps working if finances is not installed yet.
    """
    if not shop:
        return []
    try:
        return finance_bridge.services().money_accounts(shop)
    except Exception:  # noqa: BLE001 - the stock app still has to open
        logger.warning("Could not prepare the finance accounts", exc_info=True)
        return []


def _finance_options(shop):
    """The shop's active finance options: taxes, expenses, fees and the rest."""
    if not shop:
        return []
    try:
        finance_models = finance_bridge.models()

        return list(
            finance_models.FinanceOption.objects.filter(shop=shop, is_active=True).order_by(
                "kind", "name"
            )
        )
    except Exception:  # noqa: BLE001 - the stock app still has to open
        logger.warning("Could not prepare the finance options", exc_info=True)
        return []


def _can_cart(shop, user, direction):
    """Whether the person may hold a buy or a sell line."""
    if direction == CartLine.BUY:
        return _can(shop, user, "stocks.add") or _can(shop, user, "stocks.ledger.buy")
    return _can(shop, user, "stocks.move") or _can(shop, user, "stocks.ledger.sell")


def _context(request, **extra):
    user = request.user
    shop = _shop_for(user, request)
    context = {
        "shop": shop,
        "shops": _shops_for(user).order_by("name"),
        "limits": plan_limits(user) if user.is_authenticated else {},
        "product_count": shop.products.count() if shop else 0,
        "all_products": list(shop.products.order_by("name")) if shop else [],
        "finance_accounts": _finance_accounts(shop),
        "finance_options": _finance_options(shop),
        "permissions": sorted(_permissions(shop, user)),
        "can_stocks_add": _can(shop, user, "stocks.add"),
        "can_stocks_move": _can(shop, user, "stocks.move"),
        "can_cart_buy": _can_cart(shop, user, CartLine.BUY),
        "can_cart_sell": _can_cart(shop, user, CartLine.SELL),
        "cart_count": (
            cart_lines(user, shop).count() if (user.is_authenticated and shop) else 0
        ),
        "can_reports_download": _can(
            shop, user, "stocks.reports.download"
        ),
        "active": "",
    }
    context.update(extra)
    return context


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view")
def dashboard(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="dashboard"),
        )

    summary = shop_summary(shop)
    summary["stock_value_label"] = f"{shop.currency} {summary['stock_value']:,.2f}"
    summary["buying_value_label"] = f"{shop.currency} {summary['buying_value']:,.2f}"
    summary["units_label"] = f"{summary['units']:,.0f}"
    recent = shop.products.order_by("-updated_at")[:6]
    ledger = _visible_movements(
        StockMovement.objects.filter(product__shop=shop).select_related(
            "product", "created_by"
        ),
        shop,
        request.user,
    )[:8]
    orders = shop.orders.all()[:5]
    
    
    
    return render(
        request,
        "smst_stocks/dashboard.html",
        _context(
            request,
            active="dashboard",
            summary=summary,
            recent=recent,
            ledger=ledger,
            orders=orders,
            products_count=summary["products"],
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.products")
def products(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="products"),
        )

    search = request.GET.get("search", "").strip()
    state = request.GET.get("state", "").strip()

    items = shop.products.annotate(cart_total=Sum("cart_lines__quantity"))
    if search:
        items = items.filter(name__icontains=search)
    if state == "low":
        items = items.filter(
            Q(quantity__lte=0)
            | Q(reorder_level__gt=0, quantity__lte=F("reorder_level"))
        )
    elif state == "out":
        items = items.filter(quantity__lte=0)

    return render(
        request,
        "smst_stocks/products.html",
        _context(
            request,
            active="products",
            items=items,
            search=search,
            state=state,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.add")
def product_form(request, pk=None):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="products"),
        )

    product = None
    if pk:
        product = get_object_or_404(Product, pk=pk, shop__in=_shops_for(request.user))

    return render(
        request,
        "smst_stocks/product_form.html",
        _context(request, active="products", product=product),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.products")
def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("shop").annotate(
            cart_total=Sum("cart_lines__quantity")
        ),
        pk=pk,
        shop__in=_shops_for(request.user),
    )
    from .models import StockMovement

    movements = _visible_movements(
        StockMovement.objects.filter(product=product).select_related("created_by"),
        product.shop,
        request.user,
    )[:40]
    link = product.share_links.filter(is_active=True).first()
    orders = (
        product.orders.all()[:10]
        if _can(product.shop, request.user, "stocks.view.orders")
        else []
    )

    return render(
        request,
        "smst_stocks/product_detail.html",
        _context(
            request,
            active="products",
            product=product,
            movements=movements,
            share_link=link,
            orders=orders,
            holders=product_holders(product),
        ),
    )


def _cart_render(request, flash=None, receipt=None, receipts=()):
    """The cart page, or just its live part when htmx asked for it."""
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="cart"),
        )

    lines = cart_lines(request.user, shop)
    items = (
        shop.products.filter()
        .annotate(cart_total=Sum("cart_lines__quantity"))
        .order_by("name")
    )
    template = (
        "smst_stocks/partials/cart_live.html"
        if request.headers.get("HX-Target") == "cart-live"
        else "smst_stocks/cart.html"
    )
    return render(
        request,
        template,
        _context(
            request,
            active="cart",
            cart_lines=lines,
            cart_totals=cart_totals(lines),
            items=items,
            flash=flash,
            receipt=receipt,
            receipts=receipts,
        ),
    )


def _cart_flash(request, flash, shop_id):
    """Send the person back to the cart with a word on what happened."""
    getattr(messages, flash["tag"])(request, flash["text"])
    return redirect(f"{reverse('smst_stocks:cart')}?shop={shop_id}")


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view")
def cart(request):
    """The cart: what is being held, and what can be added to it."""
    return _cart_render(request)


@login_required(login_url=LOGIN_URL)
@require_POST
def cart_add(request):
    """Put a product in the cart."""
    product = get_object_or_404(
        Product, pk=request.POST.get("product"), shop__in=_shops_for(request.user)
    )
    direction = request.POST.get("direction", CartLine.SELL)
    if not _can_cart(product.shop, request.user, direction):
        raise PermissionDenied(
            "Your rank does not allow that. It needs the permission to "
            f"{'buy' if direction == CartLine.BUY else 'sell'} stock."
        )
    try:
        add_to_cart(
            request.user,
            product,
            request.POST.get("quantity"),
            direction,
            account=request.POST.get("account"),
            option_ids=request.POST.getlist("options"),
        )
        flash = {"tag": "success", "text": f"{product.name} is held in your cart."}
    except StockError as error:
        flash = {"tag": "error", "text": str(error)}

    if request.headers.get("HX-Request"):
        return _cart_render(request, flash=flash)
    return _cart_flash(request, flash, product.shop_id)


@login_required(login_url=LOGIN_URL)
@require_POST
def cart_scan(request):
    """Scan a barcode and sell one of that item straight into the cart."""
    shop = _shop_for(request.user, request)
    if shop is None:
        return redirect(reverse("smst_stocks:cart"))

    code = request.POST.get("code", "").strip()
    if not code:
        flash = {"tag": "error", "text": "Scan or type a barcode first."}
    elif not _can_cart(shop, request.user, CartLine.SELL):
        flash = {"tag": "error", "text": "Your rank does not allow selling stock."}
    else:
        product = shop.products.filter(sku__iexact=code).first()
        if product is None:
            flash = {"tag": "error", "text": f"No item has the code {code}."}
        else:
            try:
                add_to_cart(request.user, product, 1, CartLine.SELL)
                flash = {
                    "tag": "success",
                    "text": f"{product.name} is held in your cart.",
                }
            except StockError as error:
                flash = {"tag": "error", "text": str(error)}

    if request.headers.get("HX-Request"):
        return _cart_render(request, flash=flash)
    return _cart_flash(request, flash, shop.id)


@login_required(login_url=LOGIN_URL)
@require_POST
def cart_release(request, pk):
    """Let a cart line go and put its stock back."""
    line = get_object_or_404(
        CartLine, pk=pk, user=request.user, product__shop__in=_shops_for(request.user)
    )
    shop_id = line.product.shop_id
    name = line.product.name
    try:
        release_cart_line(request.user, line)
        flash = {"tag": "success", "text": f"{name} is back on the shelf."}
    except StockError as error:
        flash = {"tag": "error", "text": str(error)}

    if request.headers.get("HX-Request"):
        return _cart_render(request, flash=flash)
    return _cart_flash(request, flash, shop_id)


@login_required(login_url=LOGIN_URL)
@require_POST
def cart_process(request, pk):
    """Finish a cart line: write its movement, its receipt and its books."""
    line = get_object_or_404(
        CartLine, pk=pk, user=request.user, product__shop__in=_shops_for(request.user)
    )
    if not _can_cart(line.shop, request.user, line.direction):
        raise PermissionDenied("Your rank does not allow that.")
    shop_id = line.shop.id
    name = line.product.name
    receipt = None
    try:
        movement = process_cart_line(
            request.user,
            line,
            account=request.POST.get("account"),
            option_ids=request.POST.getlist("options"),
        )
        flash = {"tag": "success", "text": f"{name} processed and written to the books."}
        try:
            receipt = finance_bridge.receipts().create_receipt(
                line, movement, request.user
            )
        except Exception:  # noqa: BLE001 - the trade is done even if the slip is not
            logger.warning(
                "Could not write the receipt for movement %s",
                movement.pk,
                exc_info=True,
            )
    except StockError as error:
        flash = {"tag": "error", "text": str(error)}

    if request.headers.get("HX-Request"):
        response = _cart_render(request, flash=flash, receipt=receipt)
        if receipt:
            response["HX-Trigger"] = dumps(
                {
                    "receipt:print": {
                        "url": reverse(
                            "smst_finances:receipt_print", args=[receipt.pk]
                        )
                    }
                }
            )
        return response
    return _cart_flash(request, flash, shop_id)


@login_required(login_url=LOGIN_URL)
@require_POST
def cart_process_all(request):
    """Finish every line in the cart at once, with the same finances for each."""
    shop = _shop_for(request.user, request)
    if shop is None:
        return redirect(reverse("smst_stocks:cart"))

    lines = list(cart_lines(request.user, shop))
    receipts = []
    if not lines:
        flash = {"tag": "error", "text": "The cart is empty."}
    else:
        for line in lines:
            if not _can_cart(line.shop, request.user, line.direction):
                raise PermissionDenied("Your rank does not allow that.")

        done, failed = process_cart(
            request.user,
            shop,
            account=request.POST.get("account"),
            option_ids=request.POST.getlist("options"),
        )
        receipts = []
        for line, movement in done:
            try:
                receipts.append(
                    finance_bridge.receipts().create_receipt(line, movement, request.user)
                )
            except Exception:  # noqa: BLE001 - the trade is done even if the slip is not
                logger.warning(
                    "Could not write the receipt for movement %s",
                    movement.pk,
                    exc_info=True,
                )
        if failed:
            names = ", ".join(name for name, _ in failed)
            flash = {"tag": "error", "text": f"{names} stayed in the cart."}
        else:
            flash = {
                "tag": "success",
                "text": (
                    f"{len(done)} line{'s' if len(done) != 1 else ''} processed "
                    "and written to the books."
                ),
            }

    if request.headers.get("HX-Request"):
        return _cart_render(request, flash=flash, receipts=receipts)
    return _cart_flash(request, flash, shop.id)


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.movements")
def movements(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="movements"),
        )

    ledger = _visible_movements(
        StockMovement.objects.filter(product__shop=shop).select_related(
            "product", "created_by"
        ),
        shop,
        request.user,
    )
    kind = request.GET.get("kind", "").strip()
    if kind:
        ledger = ledger.filter(kind=kind)

    return render(
        request,
        "smst_stocks/movements.html",
        _context(request, active="movements", ledger=ledger[:200], kind=kind),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.low_stock")
def low_stock(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="low-stock"),
        )

    from .services import low_stock_products

    return render(
        request,
        "smst_stocks/low_stock.html",
        _context(request, active="low-stock", items=low_stock_products(shop)),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.orders")
def orders(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="orders"),
        )

    items = shop.orders.select_related("product").all()
    status = request.GET.get("status", "").strip()
    if status:
        items = items.filter(status=status)

    return render(
        request,
        "smst_stocks/orders.html",
        _context(request, active="orders", items=items, status=status),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.reports")
def reports(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request,
            "smst_stocks/empty.html",
            _context(request, active="reports"),
        )

    runs = shop.reports.select_related("created_by").all()[:20]

    return render(
        request,
        "smst_stocks/reports.html",
        _context(
            request,
            active="reports",
            runs=runs,
            report_kinds=REPORT_KINDS,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.reports.download")
def report_download(request, pk):
    run = get_object_or_404(ReportRun, pk=pk, shop__in=_shops_for(request.user))
    if not run.is_ready:
        raise Http404("That report is not ready yet.")
    response = HttpResponse(run.data, content_type=run.content_type)
    response["Content-Disposition"] = f'attachment; filename="{run.filename}"'
    return response


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.shops")
def shops(request):
    user = request.user
    return render(
        request,
        "smst_stocks/shops.html",
        _context(request, active="shops"),
    )


@login_required(login_url=LOGIN_URL)
@_requires("stocks.view.links")
def links(request):
    user = request.user
    items = ShareLink.objects.filter(shop__in=_shops_for(user)).select_related("shop", "product")
    return render(
        request,
        "smst_stocks/links.html",
        _context(request, active="links", links=items),
    )


# ----------------------------------------------------------------- public
def public_product(request, token):
    """The page a customer sees when a product is shared with them."""
    product = (
        Product.objects.select_related("shop")
        .filter(share_token=token, is_published=True)
        .first()
    )
    if not product:
        raise Http404("That item is not listed.")

    return render(
        request,
        "smst_stocks/public_product.html",
        {
            "product": product,
            "attributes": product.attribute_lines(),
            "shop": product.shop,
        },
    )


def public_shop(request, token):
    """The catalogue a shop shares."""
    shop = Shop.objects.filter(share_token=token, is_public=True).first()
    if not shop:
        raise Http404("That catalogue is not open.")

    items = shop.products.filter(is_published=True)
    return render(
        request,
        "smst_stocks/public_shop.html",
        {"shop": shop, "items": items},
    )
