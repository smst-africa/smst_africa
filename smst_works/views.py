"""The SmSt Works pages.

The pages are thin. They set up the shop the person belongs to, hand the work
to the API, and let the browser keep the timeline live over a websocket.
"""

from __future__ import annotations

import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from smst_stocks.models import Shop, StockMovement

from .models import (
    PERMISSION_GROUPS,
    PERMISSIONS,
    Customer,
    Employee,
    Guide,
    Job,
    LoyaltyTransaction,
    Supplier,
)
from .services import (
    dashboard_summary,
    ensure_default_ranks,
    has_permission,
    permissions_for,
    shops_for,
    timeline_jobs,
)

logger = logging.getLogger("smst")

LOGIN_URL = "https://user.smst.africa/"


def _shop_for(user, request):
    """The shop named in the query string, or the first the person belongs to."""
    if not user.is_authenticated:
        return None
    shop_id = request.GET.get("shop") or request.POST.get("shop")
    queryset = shops_for(user)
    if shop_id:
        shop = queryset.filter(pk=shop_id).first()
        if shop:
            return shop
    return queryset.order_by("name").first()


def _requires(permission):
    """Only open a page when the person's rank includes the view permission."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            shop = _shop_for(request.user, request)
            if shop and not has_permission(shop, request.user, permission):
                raise PermissionDenied(
                    f"Your rank does not allow that. It needs the “{permission}” permission."
                )
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def _context(request, **extra):
    user = request.user
    shop = _shop_for(user, request)
    if shop:
        ensure_default_ranks(shop)

    permissions = sorted(permissions_for(shop, user)) if shop else []
    is_owner = bool(shop and shop.owner_id == user.id)
    me = None
    if shop and not is_owner:
        me = (
            shop.employees.filter(user=user, status=Employee.HIRED)
            .select_related("rank")
            .first()
        )

    context = {
        "shop": shop,
        "shops": (
            shops_for(user) if user.is_authenticated else Shop.objects.none()
        ),
        "products": (
            list(shop.products.order_by("name")[:400]) if shop else []
        ),
        "ranks": shop.ranks.order_by("name") if shop else [],
        "permissions": permissions,
        "permission_choices": PERMISSIONS,
        "permission_groups": PERMISSION_GROUPS,
        "is_owner": bool(shop and shop.owner_id == user.id),
        "me": me,
        "my_rank": (
            "Owner"
            if is_owner
            else (me.rank.name if me and me.rank else "No rank")
        ),
        "can_stocks_add": "stocks.add" in permissions,
        "can_stocks_move": "stocks.move" in permissions,
        "can_stock_action": bool(
            {"stocks.add", "stocks.move"} & set(permissions)
        ),
        "can_customers": "customers.manage" in permissions,
        "can_suppliers": "suppliers.manage" in permissions,
        "can_jobs_create": "jobs.create" in permissions,
        "can_jobs_run": "jobs.run" in permissions,
        "can_guides": "guides.manage" in permissions,
        "can_employees": "employees.manage" in permissions,
        "can_ranks": "ranks.manage" in permissions,
        "job_statuses": Job.STATUS_CHOICES,
        "stock_kinds": tuple(
            (key, label)
            for key, label in StockMovement.KIND_CHOICES
            if (
                "stocks.add"
                if key in (StockMovement.DELIVERY, StockMovement.OPENING)
                else "stocks.move"
            )
            in permissions
        ),
        "active": "",
        "today": timezone.localdate(),
        "summary": dashboard_summary(shop) if shop else {},
    }
    context.update(extra)
    return context


@login_required(login_url=LOGIN_URL)
@_requires("works.view.dashboard")
def dashboard(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="dashboard")
        )

    return render(
        request,
        "smst_works/dashboard.html",
        _context(
            request,
            active="dashboard",
            timeline_jobs=timeline_jobs(shop, hours=24, limit=200),
            pending_jobs=(
                Job.objects.filter(shop=shop, status=Job.PENDING)
                .select_related("created_by")
                .order_by("created_at")[:20]
            ),
            recent_jobs=(
                Job.objects.filter(shop=shop)
                .select_related("created_by")
                .order_by("-created_at")[:8]
            ),
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("works.view.jobs")
def jobs(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="jobs")
        )

    items = (
        Job.objects.filter(shop=shop)
        .select_related("created_by")
        .prefetch_related("inputs__product", "outputs__product")
    )
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        items = items.filter(status=status_filter)
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(title__icontains=search)

    return render(
        request,
        "smst_works/jobs.html",
        _context(
            request,
            active="jobs",
            job_list=items.order_by("-created_at")[:400],
            status_filter=status_filter,
            search=search,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("works.view.employees")
def employees(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="employees")
        )

    items = shop.employees.select_related("rank", "user")
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        items = items.filter(status=status_filter)
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(name__icontains=search)

    return render(
        request,
        "smst_works/employees.html",
        _context(
            request,
            active="employees",
            employee_list=items.order_by("name")[:400],
            status_filter=status_filter,
            search=search,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("works.view.ranks")
def ranks(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="ranks")
        )

    return render(
        request,
        "smst_works/ranks.html",
        _context(
            request,
            active="ranks",
            rank_list=shop.ranks.prefetch_related("employees").order_by("name"),
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("works.view.customers")
def customers(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="customers")
        )

    items = Customer.objects.filter(shop=shop)
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(name__icontains=search)

    return render(
        request,
        "smst_works/customers.html",
        _context(
            request,
            active="customers",
            customer_list=items.order_by("name")[:400],
            recent_points=(
                LoyaltyTransaction.objects.filter(customer__shop=shop)
                .select_related("customer", "created_by")
                .order_by("-created_at")[:15]
            ),
            search=search,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("works.view.suppliers")
def suppliers(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="suppliers")
        )

    items = Supplier.objects.filter(shop=shop).prefetch_related("products")
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(name__icontains=search)

    return render(
        request,
        "smst_works/suppliers.html",
        _context(
            request,
            active="suppliers",
            supplier_list=items.order_by("name")[:400],
            search=search,
        ),
    )


@login_required(login_url=LOGIN_URL)
@_requires("works.view.guides")
def guides(request):
    shop = _shop_for(request.user, request)
    if shop is None:
        return render(
            request, "smst_works/empty.html", _context(request, active="guides")
        )

    items = Guide.objects.filter(shop=shop)
    category = request.GET.get("category", "").strip()
    if category:
        items = items.filter(category=category)
    search = request.GET.get("search", "").strip()
    if search:
        items = items.filter(title__icontains=search)

    return render(
        request,
        "smst_works/guides.html",
        _context(
            request,
            active="guides",
            guide_list=items.order_by("position", "title")[:400],
            categories=(
                Guide.objects.filter(shop=shop)
                .exclude(category="")
                .values_list("category", flat=True)
                .distinct()
                .order_by("category")
            ),
            category=category,
            search=search,
        ),
    )
