"""The rules behind SmSt Works.

Ranks decide what a person may do, jobs move stock from inputs to outputs, and
loyalty points are changed through one service so the balance and its history
never disagree. The services are plain Python: the API and the pages both call
them, and a failure is a message the shopkeeper can act on.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from smst_stocks.models import Product, Shop, StockMovement
from smst_stocks.services import StockError, record_movement

from .models import (
    ALL_PERMISSIONS,
    DEFAULT_RANKS,
    Customer,
    Employee,
    Job,
    JobInput,
    JobOutput,
    LoyaltyTransaction,
    Rank,
)
from .realtime import broadcast_job, broadcast_shop

logger = logging.getLogger("smst")
User = get_user_model()


class WorksError(Exception):
    """A rule was broken. The message is safe to show the user."""


# ------------------------------------------------------------------ people
def shops_for(user):
    """Every shop the user owns or works at."""
    if not user or not user.is_authenticated:
        return Shop.objects.none()
    return Shop.objects.filter(
        Q(owner=user)
        | Q(employees__user=user, employees__status=Employee.HIRED)
    ).distinct()


def permissions_for(shop, user) -> frozenset:
    """The permission keys a user has at a shop. Owners have every key."""
    if not shop or not user or not user.is_authenticated:
        return frozenset()
    if shop.owner_id == user.id:
        return frozenset(ALL_PERMISSIONS)
    employee = (
        Employee.objects.filter(shop=shop, user=user, status=Employee.HIRED)
        .select_related("rank")
        .first()
    )
    if not employee or not employee.rank:
        return frozenset()
    return frozenset(employee.rank.permissions or [])


def has_permission(shop, user, permission: str) -> bool:
    return permission in permissions_for(shop, user)


def has_any_permission(shop, user, permissions) -> bool:
    return bool(set(permissions) & permissions_for(shop, user))


def require_permission(shop, user, permission: str) -> None:
    if not has_permission(shop, user, permission):
        raise WorksError(
            f"Your rank does not allow that. It needs the “{permission}” permission."
        )


def ensure_default_ranks(shop) -> dict:
    """Create the starter ranks once. Existing ranks are left alone."""
    ranks = {}
    for name, permissions, description in DEFAULT_RANKS:
        rank, _created = Rank.objects.get_or_create(
            shop=shop,
            name=name,
            defaults={
                "permissions": list(permissions),
                "description": description,
                "is_default": True,
            },
        )
        ranks[name] = rank
    return ranks


@transaction.atomic
def hire_employee(shop, payload, actor=None):
    """Put someone on the team. A login is linked by matching email."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise WorksError("Give the employee a name.")

    email = (payload.get("email") or "").strip()
    user = payload.get("user")
    if isinstance(user, int):
        user = User.objects.filter(pk=user).first()
    if not user and email:
        user = User.objects.filter(email__iexact=email).first()

    if user and Employee.objects.filter(shop=shop, user=user).exists():
        raise WorksError("That person already works at this shop.")

    rank = payload.get("rank")
    if rank and rank.shop_id != shop.id:
        raise WorksError("That rank belongs to another shop.")

    employee = Employee.objects.create(
        shop=shop,
        user=user,
        name=name,
        phone=(payload.get("phone") or "").strip(),
        email=email,
        role=(payload.get("role") or "").strip(),
        rank=rank or None,
        status=payload.get("status") or Employee.HIRED,
        hired_at=payload.get("hired_at") or timezone.localdate(),
        notes=payload.get("notes") or "",
    )
    broadcast_shop(
        shop,
        "works.employee.created",
        {"id": employee.id, "name": employee.name},
    )
    return employee


# ------------------------------------------------------------------- jobs
def _as_id(value):
    return getattr(value, "pk", value)


def _as_quantity(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise WorksError("Enter how many items the job uses.")
    if amount <= 0:
        raise WorksError("A job line needs a quantity above zero.")
    return amount


def _product_map(shop, lines):
    ids = {_as_id(line.get("product")) for line in lines}
    products = {
        product.pk: product
        for product in Product.objects.filter(shop=shop, pk__in=ids)
    }
    for line in lines:
        if _as_id(line.get("product")) not in products:
            raise WorksError("One of the items on the job is not in your shop.")
    return products


@transaction.atomic
def create_job(shop, payload, user=None):
    """Create a pending job with the stock it will take and make."""
    title = (payload.get("title") or "").strip()
    if not title:
        raise WorksError("Give the job a name.")

    inputs = payload.get("inputs") or []
    outputs = payload.get("outputs") or []
    products = _product_map(shop, list(inputs) + list(outputs))

    input_lines = []
    for line in inputs:
        product = products[_as_id(line.get("product"))]
        input_lines.append(
            JobInput(
                product=product,
                quantity=_as_quantity(line.get("quantity")),
                note=(line.get("note") or "").strip(),
            )
        )
    output_lines = []
    for line in outputs:
        product = products[_as_id(line.get("product"))]
        output_lines.append(
            JobOutput(
                product=product,
                quantity=_as_quantity(line.get("quantity")),
                note=(line.get("note") or "").strip(),
            )
        )

    job = Job.objects.create(
        shop=shop,
        title=title,
        description=(payload.get("description") or "").strip(),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    for line in input_lines:
        line.job = job
    for line in output_lines:
        line.job = job
    JobInput.objects.bulk_create(input_lines)
    JobOutput.objects.bulk_create(output_lines)

    broadcast_job(job, "works.job.created")
    return job


@transaction.atomic
def start_job(job, user=None):
    """Start a pending job. Starting a running job changes nothing."""
    job = Job.objects.select_for_update().get(pk=job.pk)
    if job.status == Job.RUNNING:
        return job
    if job.status != Job.PENDING:
        raise WorksError("This job is already finished.")
    job.status = Job.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    broadcast_job(job, "works.job.started")
    return job


@transaction.atomic
def finish_job(job, user=None, success: bool = True, note: str = ""):
    """Finish a job. A success takes the inputs and adds the outputs."""
    job = Job.objects.select_for_update().get(pk=job.pk)
    if job.status not in Job.OPEN_STATUSES:
        raise WorksError("This job is already finished.")

    if success:
        inputs = list(job.inputs.select_related("product"))
        outputs = list(job.outputs.select_related("product"))
        ids = {line.product_id for line in inputs + outputs}
        locked = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(pk__in=ids)
        }

        for line in inputs:
            product = locked.get(line.product_id)
            if not product:
                raise WorksError("One of the input items no longer exists.")
            if product.quantity < line.quantity:
                raise WorksError(
                    f"There are only {product.quantity:g} {product.unit} of "
                    f"{product.name} in hand."
                )

        try:
            for line in inputs:
                record_movement(
                    locked[line.product_id],
                    StockMovement.ADJUSTMENT,
                    -line.quantity,
                    note=f"Job: {job.title}",
                    user=user,
                    broadcast=False,
                )
            for line in outputs:
                product = locked.get(line.product_id)
                if not product:
                    raise WorksError("One of the output items no longer exists.")
                record_movement(
                    product,
                    StockMovement.ADJUSTMENT,
                    line.quantity,
                    note=f"Job: {job.title}",
                    user=user,
                    broadcast=False,
                )
        except StockError as exc:
            raise WorksError(str(exc))

    job.finish(success=success, note=note)
    broadcast_job(
        job, "works.job.succeeded" if success else "works.job.failed"
    )
    return job


def timeline_jobs(shop, hours: int = 24, limit: int = 200):
    """The open jobs plus what finished inside the window, newest first."""
    try:
        hours = max(1, min(int(hours), 168))
    except (TypeError, ValueError):
        hours = 24
    cutoff = timezone.now() - timedelta(hours=hours)
    return (
        Job.objects.filter(shop=shop)
        .filter(
            Q(status__in=Job.OPEN_STATUSES)
            | Q(finished_at__gte=cutoff)
            | Q(created_at__gte=cutoff)
        )
        .select_related("created_by")
        .prefetch_related("inputs__product", "outputs__product")
        .order_by("-created_at")[:limit]
    )


# ---------------------------------------------------------------- loyalty
@transaction.atomic
def adjust_points(customer, points, reason: str = "", user=None):
    """Add or take away loyalty points, and keep the history line."""
    try:
        delta = int(points)
    except (TypeError, ValueError):
        raise WorksError("Enter a whole number of points.")
    if delta == 0:
        raise WorksError("Enter how many points to add or take away.")

    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if customer.points + delta < 0:
        raise WorksError(
            f"{customer.name} only has {customer.points} point"
            f"{'' if customer.points == 1 else 's'}."
        )

    customer.points = customer.points + delta
    customer.save(update_fields=["points", "updated_at"])
    transaction_line = LoyaltyTransaction.objects.create(
        customer=customer,
        kind=LoyaltyTransaction.EARN
        if delta > 0
        else LoyaltyTransaction.REDEEM,
        points=delta,
        reason=(reason or "").strip(),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    broadcast_shop(
        customer.shop,
        "works.customer.points",
        {
            "id": customer.id,
            "name": customer.name,
            "points": customer.points,
            "delta": delta,
        },
    )
    return customer, transaction_line


# ------------------------------------------------------------ shop actions
def record_shop_movement(shop, user, product, kind, quantity, note: str = ""):
    """A permission-checked stock action from the shop floor."""
    if kind not in {choice[0] for choice in StockMovement.KIND_CHOICES}:
        raise WorksError("That is not a stock action.")
    permission = (
        "stocks.add"
        if kind in (StockMovement.DELIVERY, StockMovement.OPENING)
        else "stocks.move"
    )
    require_permission(shop, user, permission)
    if product.shop_id != shop.id:
        raise WorksError("That item belongs to another shop.")

    try:
        movement = record_movement(
            product, kind, quantity, note=note or "", user=user
        )
    except StockError as exc:
        raise WorksError(str(exc))

    broadcast_shop(
        shop,
        "works.stock.moved",
        {
            "id": movement.id,
            "product": product.name,
            "kind": movement.kind,
            "quantity": float(movement.quantity),
            "balance": float(product.quantity),
        },
    )
    return movement


# ---------------------------------------------------------------- summary
def dashboard_summary(shop) -> dict:
    """The counts the dashboard and the live badge read."""
    jobs = Job.objects.filter(shop=shop)
    customers = Customer.objects.filter(shop=shop)
    points = customers.aggregate(total=Sum("points"))["total"] or 0
    return {
        "employees": Employee.objects.filter(
            shop=shop, status=Employee.HIRED
        ).count(),
        "jobs": jobs.count(),
        "pending": jobs.filter(status=Job.PENDING).count(),
        "running": jobs.filter(status=Job.RUNNING).count(),
        "succeeded": jobs.filter(status=Job.SUCCEEDED).count(),
        "failed": jobs.filter(status=Job.FAILED).count(),
        "today": jobs.filter(created_at__date=timezone.localdate()).count(),
        "customers": customers.count(),
        "points": points,
        "suppliers": shop.suppliers.count(),
        "guides": shop.guides.filter(is_published=True).count(),
        "products": shop.products.count(),
    }
