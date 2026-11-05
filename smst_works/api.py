"""The API behind SmSt Works.

Everything the app does goes through these endpoints: the team and their ranks,
loyalty customers, suppliers, guides, jobs and the permission-checked stock
actions on the shop floor. A write is checked twice: the view asks whether the
person has the permission, and the service asks again before it changes stock.
"""

from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from smst_stocks.models import Shop, StockMovement

from .models import Customer, Employee, Guide, Job, Rank, Supplier
from .realtime import broadcast_shop
from .serializers import (
    CustomerSerializer,
    EmployeeSerializer,
    GuideSerializer,
    JobCreateSerializer,
    JobSerializer,
    PointsSerializer,
    RankSerializer,
    ShopMovementSerializer,
    SupplierSerializer,
)
from .services import (
    WorksError,
    adjust_points,
    create_job,
    dashboard_summary,
    finish_job,
    has_permission,
    hire_employee,
    record_shop_movement,
    shops_for,
    start_job,
    timeline_jobs,
)

logger = logging.getLogger("smst")


def error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


def request_shop(request, data=None, required=True):
    """The shop named in the request, if the person belongs to it."""
    data = data if data is not None else getattr(request, "data", {}) or {}
    shop_id = request.query_params.get("shop") or data.get("shop")
    queryset = shops_for(request.user)
    if isinstance(shop_id, Shop):
        shop_id = shop_id.pk
    shop = None
    if shop_id:
        try:
            shop = queryset.filter(pk=shop_id).first()
        except (TypeError, ValueError):
            shop = None
    else:
        shop = queryset.order_by("name").first()
    if not shop and required:
        raise WorksError("Start a shop in SmSt Stocks first.")
    return shop


def _forbidden(permission: str):
    return PermissionDenied(
        f"Your rank does not allow that. It needs the “{permission}” permission."
    )


class WorksScopedViewSet(viewsets.ModelViewSet):
    """A viewset whose records always belong to one of the person's shops."""

    permission_classes = [IsAuthenticated]
    view_permission = None

    def get_queryset(self):
        shop = request_shop(self.request, required=False)
        if (
            shop
            and self.view_permission
            and not has_permission(shop, self.request.user, self.view_permission)
        ):
            raise _forbidden(self.view_permission)
        base = super().get_queryset()
        return base.filter(shop=shop) if shop else base.none()

    def _shop_for_write(self, data=None):
        try:
            return request_shop(self.request, data or {})
        except WorksError as exc:
            raise ValidationError({"detail": str(exc)})

    def _require(self, shop, permission: str):
        if not has_permission(shop, self.request.user, permission):
            raise _forbidden(permission)


# ------------------------------------------------------------------ ranks
class RankViewSet(WorksScopedViewSet):
    view_permission = "works.view.ranks"
    serializer_class = RankSerializer
    queryset = Rank.objects.all()

    def get_queryset(self):
        return super().get_queryset().order_by("name")

    def _unique_name(self, shop, name, exclude=None):
        matches = Rank.objects.filter(shop=shop, name=name)
        if exclude:
            matches = matches.exclude(pk=exclude.pk)
        if matches.exists():
            raise ValidationError({"name": "A rank with that name already exists."})

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        self._require(shop, "ranks.manage")
        self._unique_name(shop, serializer.validated_data["name"])
        serializer.save(shop=shop)
        broadcast_shop(
            shop,
            "works.rank.created",
            {"id": serializer.instance.id, "name": serializer.instance.name},
        )

    def perform_update(self, serializer):
        rank = self.get_object()
        self._require(rank.shop, "ranks.manage")
        name = serializer.validated_data.get("name", rank.name)
        self._unique_name(rank.shop, name, exclude=rank)
        serializer.save()
        broadcast_shop(
            rank.shop,
            "works.rank.updated",
            {"id": rank.id, "name": rank.name},
        )

    def perform_destroy(self, instance):
        self._require(instance.shop, "ranks.manage")
        shop = instance.shop
        name = instance.name
        instance.delete()
        broadcast_shop(shop, "works.rank.deleted", {"id": None, "name": name})


# -------------------------------------------------------------- employees
class EmployeeViewSet(WorksScopedViewSet):
    view_permission = "works.view.employees"
    serializer_class = EmployeeSerializer
    queryset = Employee.objects.select_related("rank", "user").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("name")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            shop = request_shop(request, request.data)
        except WorksError as exc:
            return error(str(exc))
        if not has_permission(shop, request.user, "employees.manage"):
            raise _forbidden("employees.manage")
        try:
            employee = hire_employee(
                shop, serializer.validated_data, request.user
            )
        except WorksError as exc:
            return error(str(exc))
        return Response(
            self.get_serializer(employee).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        employee = self.get_object()
        self._require(employee.shop, "employees.manage")
        rank = serializer.validated_data.get("rank")
        if rank and rank.shop_id != employee.shop_id:
            raise ValidationError({"rank": "That rank belongs to another shop."})
        serializer.save()
        broadcast_shop(
            employee.shop,
            "works.employee.updated",
            {"id": employee.id, "name": employee.name},
        )

    def perform_destroy(self, instance):
        self._require(instance.shop, "employees.manage")
        shop = instance.shop
        name = instance.name
        instance.delete()
        broadcast_shop(shop, "works.employee.deleted", {"id": None, "name": name})


# -------------------------------------------------------------- customers
class CustomerViewSet(WorksScopedViewSet):
    view_permission = "works.view.customers"
    serializer_class = CustomerSerializer
    queryset = Customer.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        tier = self.request.query_params.get("tier")
        if tier == "gold":
            queryset = queryset.filter(points__gte=500)
        elif tier == "silver":
            queryset = queryset.filter(points__gte=200, points__lt=500)
        elif tier == "bronze":
            queryset = queryset.filter(points__lt=200)
        return queryset.order_by("name")

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        self._require(shop, "customers.manage")
        serializer.save(shop=shop)
        broadcast_shop(
            shop,
            "works.customer.created",
            {"id": serializer.instance.id, "name": serializer.instance.name},
        )

    def perform_update(self, serializer):
        customer = self.get_object()
        self._require(customer.shop, "customers.manage")
        serializer.save()
        broadcast_shop(
            customer.shop,
            "works.customer.updated",
            {"id": customer.id, "name": customer.name},
        )

    def perform_destroy(self, instance):
        self._require(instance.shop, "customers.manage")
        shop = instance.shop
        name = instance.name
        instance.delete()
        broadcast_shop(shop, "works.customer.deleted", {"id": None, "name": name})

    @action(detail=True, methods=["post"])
    def points(self, request, pk=None):
        customer = self.get_object()
        if not has_permission(
            customer.shop, request.user, "customers.manage"
        ):
            raise _forbidden("customers.manage")
        serializer = PointsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            customer, _line = adjust_points(
                customer,
                serializer.validated_data["points"],
                serializer.validated_data.get("reason", ""),
                request.user,
            )
        except WorksError as exc:
            return error(str(exc))
        return Response(self.get_serializer(customer).data)


# --------------------------------------------------------------- suppliers
class SupplierViewSet(WorksScopedViewSet):
    view_permission = "works.view.suppliers"
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.prefetch_related("products").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("name")

    def _check_products(self, shop, products):
        if any(product.shop_id != shop.id for product in products):
            raise ValidationError(
                {"products": "Every linked item must be in this shop."}
            )

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        self._require(shop, "suppliers.manage")
        self._check_products(
            shop, serializer.validated_data.get("products") or []
        )
        serializer.save(shop=shop)
        broadcast_shop(
            shop,
            "works.supplier.created",
            {"id": serializer.instance.id, "name": serializer.instance.name},
        )

    def perform_update(self, serializer):
        supplier = self.get_object()
        self._require(supplier.shop, "suppliers.manage")
        self._check_products(
            supplier.shop, serializer.validated_data.get("products") or []
        )
        serializer.save()
        broadcast_shop(
            supplier.shop,
            "works.supplier.updated",
            {"id": supplier.id, "name": supplier.name},
        )

    def perform_destroy(self, instance):
        self._require(instance.shop, "suppliers.manage")
        shop = instance.shop
        name = instance.name
        instance.delete()
        broadcast_shop(shop, "works.supplier.deleted", {"id": None, "name": name})


# ----------------------------------------------------------------- guides
class GuideViewSet(WorksScopedViewSet):
    view_permission = "works.view.guides"
    serializer_class = GuideSerializer
    queryset = Guide.objects.select_related("updated_by").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(title__icontains=search)
        shop_id = self.request.query_params.get("shop")
        if shop_id:
            shop = (
                shops_for(self.request.user)
                .filter(pk=shop_id)
                .first()
            )
            if shop and not has_permission(
                shop, self.request.user, "guides.manage"
            ):
                queryset = queryset.filter(is_published=True)
        return queryset.order_by("position", "title")

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        self._require(shop, "guides.manage")
        serializer.save(shop=shop, updated_by=self.request.user)
        broadcast_shop(
            shop,
            "works.guide.created",
            {"id": serializer.instance.id, "title": serializer.instance.title},
        )

    def perform_update(self, serializer):
        guide = self.get_object()
        self._require(guide.shop, "guides.manage")
        serializer.save(updated_by=self.request.user)
        broadcast_shop(
            guide.shop,
            "works.guide.updated",
            {"id": guide.id, "title": guide.title},
        )

    def perform_destroy(self, instance):
        self._require(instance.shop, "guides.manage")
        shop = instance.shop
        title = instance.title
        instance.delete()
        broadcast_shop(shop, "works.guide.deleted", {"id": None, "title": title})


# ------------------------------------------------------------------- jobs
class JobViewSet(WorksScopedViewSet):
    view_permission = "works.view.jobs"
    serializer_class = JobSerializer
    queryset = (
        Job.objects.select_related("created_by")
        .prefetch_related("inputs__product", "outputs__product")
        .all()
    )
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(title__icontains=search)
        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            shop = request_shop(request, request.data)
        except WorksError as exc:
            return error(str(exc))
        if not has_permission(shop, request.user, "jobs.create"):
            raise _forbidden("jobs.create")
        try:
            job = create_job(shop, serializer.validated_data, request.user)
        except WorksError as exc:
            return error(str(exc))
        return Response(
            JobSerializer(job).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        job = self.get_object()
        if not has_permission(job.shop, request.user, "jobs.run"):
            raise _forbidden("jobs.run")
        try:
            job = start_job(job, request.user)
        except WorksError as exc:
            return error(str(exc))
        return Response(JobSerializer(job).data)

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        job = self.get_object()
        if not has_permission(job.shop, request.user, "jobs.run"):
            raise _forbidden("jobs.run")
        success = request.data.get("success", True)
        if isinstance(success, str):
            success = success.lower() not in ("false", "0", "no", "failed")
        try:
            job = finish_job(
                job,
                request.user,
                success=bool(success),
                note=request.data.get("note", ""),
            )
        except WorksError as exc:
            return error(str(exc))
        return Response(JobSerializer(job).data)


# -------------------------------------------------------------- live views
class TimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            shop = request_shop(request)
        except WorksError as exc:
            return error(str(exc), status.HTTP_404_NOT_FOUND)
        if not has_permission(shop, request.user, "works.view.dashboard"):
            raise _forbidden("works.view.dashboard")
        try:
            hours = int(request.query_params.get("hours") or 24)
        except (TypeError, ValueError):
            hours = 24
        jobs = timeline_jobs(shop, hours=hours)
        return Response(
            {
                "now": timezone.now().isoformat(),
                "hours": max(1, min(hours, 168)),
                "shop": shop.id,
                "jobs": JobSerializer(jobs, many=True).data,
                "summary": dashboard_summary(shop),
            }
        )


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            shop = request_shop(request)
        except WorksError as exc:
            return error(str(exc), status.HTTP_404_NOT_FOUND)
        if not has_permission(shop, request.user, "works.view.dashboard"):
            raise _forbidden("works.view.dashboard")
        return Response(dashboard_summary(shop))


class ShopMovementView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ShopMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            shop = request_shop(request, request.data)
        except WorksError as exc:
            return error(str(exc))
        permission = (
            "stocks.add"
            if data["kind"]
            in (StockMovement.DELIVERY, StockMovement.OPENING)
            else "stocks.move"
        )
        if not has_permission(shop, request.user, permission):
            raise _forbidden(permission)
        try:
            movement = record_shop_movement(
                shop,
                request.user,
                data["product"],
                data["kind"],
                data["quantity"],
                data.get("note", ""),
            )
        except WorksError as exc:
            return error(str(exc))
        return Response(
            {
                "id": movement.id,
                "kind": movement.kind,
                "quantity": float(movement.quantity),
                "product": movement.product_id,
                "product_name": movement.product.name,
                "unit": movement.product.unit,
                "balance": float(movement.product.quantity),
            },
            status=status.HTTP_201_CREATED,
        )
