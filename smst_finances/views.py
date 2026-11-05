"""The SmSt Finances pages.

The pages are thin. They set up the shop, hand the work to the API and let the
browser keep the numbers live over a websocket.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from smst_stocks.models import Product, Shop, StockMovement
from smst_stocks.services import plan_limits

from .models import (
    FinanceAccount,
    FinanceBudget,
    FinanceChart,
    FinanceEntry,
    FinanceOption,
    FinanceReport,
    Receipt,
)
from .services import (
    balance_sheet,
    budget_status,
    cash_flow,
    dashboard_summary,
    ensure_default_accounts,
    general_ledger,
    profit_and_loss,
    trial_balance,
)

logger = logging.getLogger("smst")

LOGIN_URL = "https://user.smst.africa/"

REPORT_KINDS = [
    (
        FinanceReport.INCOME,
        "Income",
        "Every sale, profit and other money that came in.",
    ),
    (
        FinanceReport.EXPENSES,
        "Expenses",
        "What the shop spent, including losses, discounts and refunds.",
    ),
    (
        FinanceReport.PROFIT_LOSS,
        "Profit and loss",
        "Income against expenses, and what was left at the end.",
    ),
    (FinanceReport.TAX, "Tax", "Tax collected, and the tax still owed."),
    (
        FinanceReport.CASH_FLOW,
        "Cash flow",
        "What moved through the till and the bank, line by line.",
    ),
    (
        FinanceReport.TRIAL_BALANCE,
        "Trial balance",
        "Every account with its debits and credits, and whether they agree.",
    ),
    (
        FinanceReport.BALANCE_SHEET,
        "Balance sheet",
        "What the shop owns, what it owes, and what belongs to the owner.",
    ),
    (
        FinanceReport.GENERAL_LEDGER,
        "General ledger",
        "Every posted entry and the two sides it moved.",
    ),
    (
        FinanceReport.BUDGETS,
        "Budgets",
        "Each plan, what has been spent and what is left.",
    ),
]

STATEMENT_KINDS = [
    ("profit_loss", "Profit and loss"),
    ("balance_sheet", "Balance sheet"),
    ("trial_balance", "Trial balance"),
    ("cash_flow", "Cash flow"),
    ("general_ledger", "General ledger"),
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


def _visible_entries(queryset, shop, user):
    if _can(shop, user, "finances.entries.all"):
        return queryset
    return queryset.filter(created_by=user)


def _limits(user):
    try:
        return plan_limits(user)
    except Exception:  # noqa: BLE001
        return {"plan": "free", "shops": 1, "items_per_shop": 50}


def _context(request, **extra):
    user = request.user
    shop = _shop_for(user, request)
    if shop:
        ensure_default_accounts(shop)

    context = {
        "shop": shop,
        "shops": _shops_for(user).order_by("name"),
        "limits": _limits(user) if user.is_authenticated else {},
        "product_count": shop.products.count() if shop else 0,
        "permissions": sorted(_permissions(shop, user)),
        "can_manage": _can(shop, user, "finances.manage"),
        "can_generate_graphs": _can(
            shop, user, "finances.graphs.generate"
        ),
        "can_download_reports": _can(
            shop, user, "finances.reports.download"
        ),
        "all_products": (
            list(shop.products.order_by("name")[:400]) if shop else []
        ),
        "accounts": (
            FinanceAccount.objects.filter(shop=shop).order_by("type", "code")
            if shop
            else []
        ),
        "finance_options": (
            FinanceOption.objects.filter(shop=shop, is_active=True).order_by(
                "kind", "name"
            )
            if shop
            else []
        ),
        "recent_movements": (
            StockMovement.objects.filter(product__shop=shop)
            .select_related("product")
            .order_by("-created_at")[:200]
            if shop
            else []
        ),
        "entry_kinds": FinanceEntry.KIND_CHOICES,
        "entry_statuses": FinanceEntry.STATUS_CHOICES,
        "active": "",
        "today": timezone.localdate(),
    }
    context.update(extra)
    return context


def _month_start():
    today = timezone.localdate()
    return today.replace(day=1)


def _parse_period(request):
    default_start = _month_start()
    default_end = timezone.localdate()
    date_from = parse_date(str(request.GET.get("date_from") or "")) or default_start
    date_to = parse_date(str(request.GET.get("date_to") or "")) or default_end
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.dashboard")
def dashboard(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="dashboard"))

    date_from, date_to = _parse_period(request)
    summary = dashboard_summary(shop, date_from, date_to)

    entries = _visible_entries(
        FinanceEntry.objects.filter(
            shop=shop,
            status=FinanceEntry.POSTED,
            occurred_at__date__gte=date_to - timedelta(days=89),
            occurred_at__date__lte=date_to,
        ).select_related("option", "product", "movement"),
        shop,
        request.user,
    )

    recent = _visible_entries(
        FinanceEntry.objects.filter(shop=shop).select_related(
            "option", "product", "account"
        ),
        shop,
        request.user,
    )[:8]

    expense_groups = {}
    for entry in entries:
        if entry.kind not in (
            FinanceEntry.EXPENSE,
            FinanceEntry.LOSS,
            FinanceEntry.DISCOUNT,
            FinanceEntry.REFUND,
        ):
            continue
        label = entry.option.name if entry.option else entry.get_kind_display()
        expense_groups[label] = expense_groups.get(label, Decimal("0")) + entry.amount

    return render(
        request,
        "smst_finances/dashboard.html",
        _context(
            request,
            active="dashboard",
            summary=summary,
            recent=recent,
            chart_entries=entries[:500],
            expense_groups=sorted(
                expense_groups.items(), key=lambda item: item[1], reverse=True
            )[:7],
            date_from=date_from,
            date_to=date_to,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.entries")
def entries(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="entries"))

    items = _visible_entries(
        FinanceEntry.objects.filter(shop=shop).select_related(
            "option", "product", "movement", "account", "payment_account"
        ),
        shop,
        request.user,
    )
    kind = request.GET.get("kind", "").strip()
    if kind:
        items = items.filter(kind=kind)
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        items = items.filter(status=status_filter)
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(description__icontains=search)
    date_from, date_to = _parse_period(request)
    items = items.filter(
        occurred_at__date__gte=date_from, occurred_at__date__lte=date_to
    )

    return render(
        request,
        "smst_finances/entries.html",
        _context(
            request,
            active="entries",
            items=items[:400],
            kind=kind,
            status=status_filter,
            search=search,
            date_from=date_from,
            date_to=date_to,
            entry_kinds=FinanceEntry.KIND_CHOICES,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.options")
def options(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="options"))

    items = FinanceOption.objects.filter(shop=shop).select_related("account")
    kind = request.GET.get("kind", "").strip()
    if kind:
        items = items.filter(kind=kind)
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(name__icontains=search)

    return render(
        request,
        "smst_finances/options.html",
        _context(
            request,
            active="options",
            items=items,
            kind=kind,
            search=search,
            option_kinds=FinanceOption.KIND_CHOICES,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.accounts")
def accounts(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="accounts"))

    items = FinanceAccount.objects.filter(shop=shop)
    account_type = request.GET.get("type", "").strip()
    if account_type:
        items = items.filter(type=account_type)

    return render(
        request,
        "smst_finances/accounts.html",
        _context(
            request,
            active="accounts",
            items=items,
            account_type=account_type,
            account_types=FinanceAccount.TYPE_CHOICES,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.statements")
def statements(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="statements"))

    date_from, date_to = _parse_period(request)
    kind = request.GET.get("kind", "profit_loss").strip()
    if kind not in {choice[0] for choice in STATEMENT_KINDS}:
        kind = "profit_loss"

    if kind == "trial_balance":
        statement = trial_balance(shop, date_from, date_to)
    elif kind == "balance_sheet":
        statement = balance_sheet(shop, date_from, date_to)
    elif kind == "cash_flow":
        statement = cash_flow(shop, date_from, date_to)
    elif kind == "general_ledger":
        statement = general_ledger(shop, date_from, date_to)
    else:
        statement = profit_and_loss(shop, date_from, date_to)

    if kind == "balance_sheet":
        statement["liabilities_equity_total"] = (
            statement["liabilities_total"] + statement["equity_total"]
        )
    if kind == "trial_balance":
        statement["difference"] = (
            statement["total_debit"] - statement["total_credit"]
        )

    return render(
        request,
        "smst_finances/statements.html",
        _context(
            request,
            active="statements",
            statement=statement,
            statement_kind=kind,
            statement_kinds=STATEMENT_KINDS,
            date_from=date_from,
            date_to=date_to,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.charts")
def charts(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="charts"))

    saved = FinanceChart.objects.filter(shop=shop).select_related("created_by")
    date_from, date_to = _parse_period(request)

    return render(
        request,
        "smst_finances/charts.html",
        _context(
            request,
            active="charts",
            charts=saved,
            chart_types=FinanceChart.TYPE_CHOICES,
            x_sources=FinanceChart.X_CHOICES,
            y_sources=FinanceChart.Y_CHOICES,
            date_from=date_from,
            date_to=date_to,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.budgets")
def budgets(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="budgets"))

    items = []
    for budget in FinanceBudget.objects.filter(shop=shop).select_related(
        "account", "option"
    ):
        items.append({"budget": budget, "status": budget_status(budget)})

    return render(
        request,
        "smst_finances/budgets.html",
        _context(
            request,
            active="budgets",
            items=items,
            budget_periods=FinanceBudget.PERIOD_CHOICES,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.reports")
def reports(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(request, "smst_finances/empty.html", _context(request, active="reports"))

    runs = FinanceReport.objects.filter(shop=shop).select_related("created_by")[:30]

    return render(
        request,
        "smst_finances/reports.html",
        _context(
            request,
            active="reports",
            runs=runs,
            report_kinds=REPORT_KINDS,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.reports.download")
def report_download(request, pk):
    run = get_object_or_404(FinanceReport, pk=pk, shop__in=_shops_for(request.user))
    if not run.is_ready:
        raise Http404("That report is not ready yet.")
    response = HttpResponse(run.data, content_type=run.content_type)
    response["Content-Disposition"] = f'attachment; filename="{run.filename}"'
    return response


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.entries")
def receipts(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_finances/empty.html", _context(request, active="receipts")
        )

    items = (
        Receipt.objects.filter(shop=shop)
        .select_related("created_by", "movement")
        .order_by("-created_at")[:60]
    )
    return render(
        request,
        "smst_finances/receipts.html",
        _context(request, active="receipts", receipts=items),
    )


def _receipt_for(user, pk):
    return get_object_or_404(Receipt, pk=pk, shop__in=_shops_for(user))


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.entries")
def receipt_print(request, pk):
    receipt = _receipt_for(request.user, pk)
    return render(
        request,
        "smst_finances/receipt.html",
        {"receipt": receipt, "details": receipt.details},
    )


@login_required(login_url=LOGIN_URL)
@_requires("finances.view.entries")
def receipt_download(request, pk):
    receipt = _receipt_for(request.user, pk)
    if not receipt.content:
        raise Http404("That receipt has no file.")
    response = HttpResponse(receipt.data, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{receipt.filename or receipt.reference + ".pdf"}"'
    )
    return response
