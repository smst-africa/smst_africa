"""The API behind SmSt Finances.

Everything the app does goes through these endpoints: the chart of accounts,
finance options, entries, budgets, graphs and reports. Entries are written
through the service layer so the double-entry book never falls out of step.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from smst_stocks.models import Order, Product, Shop, StockMovement

from .models import (
    FinanceAccount,
    FinanceBudget,
    FinanceChart,
    FinanceEntry,
    FinanceOption,
    FinanceReport,
)
from .realtime import (
    broadcast_chart,
    broadcast_entry,
    broadcast_option,
    broadcast_shop,
)
from .serializers import (
    FinanceAccountSerializer,
    FinanceBudgetSerializer,
    FinanceChartSerializer,
    FinanceEntrySerializer,
    FinanceOptionSerializer,
    FinanceReportSerializer,
)
from .services import (
    FinanceError,
    balance_sheet,
    cash_flow,
    chart_data,
    create_entry,
    dashboard_summary,
    delete_entry,
    general_ledger,
    profit_and_loss,
    trial_balance,
    update_entry,
    void_entry,
)

logger = logging.getLogger("smst")


def error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


def _shops_for(user):
    """Every shop the user owns or works at."""
    if not user or not user.is_authenticated:
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


def _require(shop, user, permission):
    if not _can(shop, user, permission):
        raise PermissionDenied(
            f"Your rank does not allow that. It needs the “{permission}” permission."
        )


def _shop_for_request(request):
    shop_id = request.query_params.get("shop")
    if not shop_id and hasattr(request, "data"):
        shop_id = request.data.get("shop")
    queryset = _shops_for(request.user)
    if shop_id:
        return queryset.filter(pk=shop_id).first()
    return queryset.order_by("name").first()


def _visible_entries(queryset, shop, user):
    if _can(shop, user, "finances.entries.all"):
        return queryset
    return queryset.filter(created_by=user)


def request_shop(request, data=None, required=True):
    data = data or {}
    shop_id = request.query_params.get("shop") or data.get("shop")
    queryset = _shops_for(request.user)
    if isinstance(shop_id, Shop):
        shop_id = str(shop_id.id)
    
    
    if shop_id:
        shop = queryset.filter(pk=shop_id).first()
    else:
        shop = queryset.order_by("name").first()
    if not shop and required:
        raise FinanceError("Start a shop in SmSt Stocks first.")
    return shop


class ShopScopedViewSet(viewsets.ModelViewSet):
    """A viewset whose records always belong to one of the user's shops."""

    permission_classes = [IsAuthenticated]
    view_permission = None
    write_permission = "finances.manage"

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop and self.view_permission:
            _require(shop, self.request.user, self.view_permission)
        base = super().get_queryset()
        return base.filter(shop=shop) if shop else base.none()

    def _shop_for_write(self, data=None):
        shop = request_shop(self.request, data or {})
        given = (data or {}).get("shop")
        if isinstance(given, Shop):
            given = given.id
        if given and str(given) != str(shop.pk):
            raise FinanceError("That shop is not yours.")
        if self.write_permission:
            _require(shop, self.request.user, self.write_permission)
        return shop


# ---------------------------------------------------------------- accounts
class FinanceAccountViewSet(ShopScopedViewSet):
    view_permission = "finances.view.accounts"
    serializer_class = FinanceAccountSerializer
    queryset = FinanceAccount.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        account_type = self.request.query_params.get("type")
        if account_type:
            queryset = queryset.filter(type=account_type)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("type", "code")

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        serializer.save(shop=shop)
        broadcast_shop(
            shop,
            "finance.account.created",
            {"id": serializer.instance.id, "name": serializer.instance.name},
        )

    def perform_update(self, serializer):
        account = self.get_object()
        _require(account.shop, self.request.user, "finances.manage")
        data = serializer.validated_data
        if "shop" in data and not _shops_for(self.request.user).filter(
            pk=data["shop"].pk
        ).exists():
            raise FinanceError("That shop is not yours.")
        if "code" in data and data["code"] != account.code and account.is_system:
            raise FinanceError("A built-in account keeps its code.")
        serializer.save()
        broadcast_shop(
            account.shop,
            "finance.account.updated",
            {"id": account.id, "name": account.name},
        )

    def perform_destroy(self, instance):
        _require(instance.shop, self.request.user, "finances.manage")
        if instance.is_system:
            raise FinanceError("A built-in account cannot be deleted.")
        if instance.journal_lines.exists():
            raise FinanceError(
                "This account has entries. Rename it instead of deleting it."
            )
        shop = instance.shop
        instance.delete()
        broadcast_shop(
            shop,
            "finance.account.deleted",
            {"id": instance.id, "name": instance.name},
        )


# ----------------------------------------------------------------- options
class FinanceOptionViewSet(ShopScopedViewSet):
    view_permission = "finances.view.options"
    serializer_class = FinanceOptionSerializer
    queryset = FinanceOption.objects.select_related("account").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        kind = self.request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(kind=kind)
        applies_to = self.request.query_params.get("applies_to")
        if applies_to:
            queryset = queryset.filter(applies_to__in=(applies_to, FinanceOption.ALL))
        active = self.request.query_params.get("active")
        if active in ("true", "1"):
            queryset = queryset.filter(is_active=True)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("kind", "name")

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        account = serializer.validated_data.get("account")
        if account and account.shop_id != shop.id:
            raise FinanceError("That account belongs to another shop.")
        serializer.save(shop=shop)
        broadcast_option(serializer.instance, "finance.option.created")

    def perform_update(self, serializer):
        option = self.get_object()
        _require(option.shop, self.request.user, "finances.manage")
        account = serializer.validated_data.get("account")
        if account and account.shop_id != option.shop_id:
            raise FinanceError("That account belongs to another shop.")
        serializer.save()
        broadcast_option(option)

    def perform_destroy(self, instance):
        _require(instance.shop, self.request.user, "finances.manage")
        shop = instance.shop
        name = instance.name
        instance.delete()
        broadcast_shop(
            shop, "finance.option.deleted", {"id": instance.id, "name": name}
        )


# ----------------------------------------------------------------- entries
def entry_payload(request, partial=False):
    data = request.data
    payload = {}

    def put(name, value):
        payload[name] = value

    if not partial or "kind" in data:
        put("kind", data.get("kind") or FinanceEntry.EXPENSE)
    if not partial or "status" in data:
        put("status", data.get("status") or FinanceEntry.POSTED)
    if not partial or "amount" in data:
        put("amount", data.get("amount") or 0)
    if not partial or "base_amount" in data:
        put("base_amount", data.get("base_amount"))
    if not partial or "rate" in data:
        put("rate", data.get("rate"))
    if not partial or "description" in data:
        put("description", data.get("description") or "")
    if not partial or "note" in data:
        put("note", data.get("note") or "")
    if not partial or "shop" in data:
        put("shop", data.get("shop"))

    for name in ("option", "product", "movement", "order", "account", "payment_account"):
        if not partial or name in data:
            value = data.get(name)
            if value in (None, ""):
                put(name, None)
                continue
            if name == "option":
                obj = get_object_or_404(
                    FinanceOption, pk=value, shop__in=_shops_for(request.user)
                )
            elif name == "product":
                obj = get_object_or_404(
                    Product, pk=value, shop__in=_shops_for(request.user)
                )
            elif name == "movement":
                obj = get_object_or_404(
                    StockMovement, pk=value, product__shop__in=_shops_for(request.user)
                )
            elif name == "order":
                obj = get_object_or_404(Order, pk=value, shop__in=_shops_for(request.user))
            elif name == "account":
                obj = get_object_or_404(
                    FinanceAccount, pk=value, shop__in=_shops_for(request.user)
                )
            else:
                obj = get_object_or_404(
                    FinanceAccount, pk=value, shop__in=_shops_for(request.user)
                )
            put(name, obj)

    if "occurred_at" in data and data.get("occurred_at"):
        value = data.get("occurred_at")
        parsed = parse_datetime(str(value))
        if parsed is None:
            day = parse_date(str(value)[:10])
            if day is None:
                raise FinanceError("That date could not be read.")
            from django.utils import timezone

            parsed = timezone.make_aware(
                timezone.datetime.combine(day, timezone.datetime.min.time())
            )
        put("occurred_at", parsed)

    return payload


class FinanceEntryViewSet(ShopScopedViewSet):
    view_permission = "finances.view.entries"
    serializer_class = FinanceEntrySerializer
    queryset = FinanceEntry.objects.select_related(
        "option", "product", "movement", "order", "account", "payment_account"
    ).prefetch_related("lines__account")

    def get_queryset(self):
        queryset = super().get_queryset()
        shop = _shop_for_request(self.request)
        queryset = _visible_entries(queryset, shop, self.request.user)
        kind = self.request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(kind=kind)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        option = self.request.query_params.get("option")
        if option:
            queryset = queryset.filter(option_id=option)
        account = self.request.query_params.get("account")
        if account:
            queryset = queryset.filter(account_id=account)
        product = self.request.query_params.get("product")
        if product:
            queryset = queryset.filter(product_id=product)
        movement = self.request.query_params.get("movement")
        if movement:
            queryset = queryset.filter(movement_id=movement)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                description__icontains=search
            ) | queryset.filter(reference__icontains=search)
        date_from = self.request.query_params.get("date_from")
        if date_from:
            queryset = queryset.filter(occurred_at__date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            queryset = queryset.filter(occurred_at__date__lte=date_to)
        return queryset.order_by("-occurred_at", "-id")

    def create(self, request, *args, **kwargs):
        try:
            payload = entry_payload(request)
            shop = request_shop(request, payload)
            _require(shop, request.user, "finances.manage")
            payload.pop("shop", None)
            entry = create_entry(shop, payload, user=request.user)
        except FinanceError as exc:
            return error(str(exc))
        broadcast_entry(entry, "finance.entry.created")
        return Response(
            FinanceEntrySerializer(entry).data, status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        entry = self.get_object()
        _require(entry.shop, request.user, "finances.manage")
        try:
            payload = entry_payload(request, partial=kwargs.get("partial", False))
            payload.pop("shop", None)
            entry = update_entry(entry, payload)
        except FinanceError as exc:
            return error(str(exc))
        broadcast_entry(entry, "finance.entry.updated")
        return Response(FinanceEntrySerializer(entry).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        entry = self.get_object()
        _require(entry.shop, request.user, "finances.manage")
        shop = entry.shop
        reference = entry.reference
        delete_entry(entry)
        broadcast_shop(
            shop,
            "finance.entry.deleted",
            {"id": kwargs.get("pk"), "reference": reference},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        entry = self.get_object()
        _require(entry.shop, request.user, "finances.manage")
        entry = void_entry(entry)
        broadcast_entry(entry, "finance.entry.voided")
        return Response(FinanceEntrySerializer(entry).data)


# ----------------------------------------------------------------- budgets
class FinanceBudgetViewSet(ShopScopedViewSet):
    view_permission = "finances.view.budgets"
    serializer_class = FinanceBudgetSerializer
    queryset = FinanceBudget.objects.select_related("account", "option").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        period = self.request.query_params.get("period")
        if period:
            queryset = queryset.filter(period=period)
        return queryset.order_by("-starts_on", "name")

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        serializer.save(shop=shop, created_by=self.request.user)
        broadcast_shop(
            shop,
            "finance.budget.created",
            {"id": serializer.instance.id, "name": serializer.instance.name},
        )

    def perform_update(self, serializer):
        budget = self.get_object()
        _require(budget.shop, self.request.user, "finances.manage")
        serializer.save()
        broadcast_shop(
            budget.shop,
            "finance.budget.updated",
            {"id": budget.id, "name": budget.name},
        )

    def perform_destroy(self, instance):
        _require(instance.shop, self.request.user, "finances.manage")
        shop = instance.shop
        name = instance.name
        instance.delete()
        broadcast_shop(
            shop, "finance.budget.deleted", {"id": instance.id, "name": name}
        )


# ------------------------------------------------------------------ charts
class FinanceChartViewSet(ShopScopedViewSet):
    view_permission = "finances.view.charts"
    serializer_class = FinanceChartSerializer
    queryset = FinanceChart.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        chart_type = self.request.query_params.get("chart_type")
        if chart_type:
            queryset = queryset.filter(chart_type=chart_type)
        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        shop = self._shop_for_write(serializer.validated_data)
        serializer.save(shop=shop, created_by=self.request.user)
        broadcast_chart(serializer.instance, "finance.chart.created")

    def perform_update(self, serializer):
        chart = self.get_object()
        _require(chart.shop, self.request.user, "finances.manage")
        serializer.save()
        broadcast_chart(chart)

    def perform_destroy(self, instance):
        _require(instance.shop, self.request.user, "finances.manage")
        shop = instance.shop
        title = instance.title
        instance.delete()
        broadcast_shop(
            shop, "finance.chart.deleted", {"id": instance.id, "title": title}
        )

    @action(detail=False, methods=["post"])
    def preview(self, request):
        try:
            shop = request_shop(request, request.data)
            _require(shop, request.user, "finances.graphs.generate")
            data = chart_data(
                shop,
                x_source=request.data.get("x_source", FinanceChart.TIME),
                y_source=request.data.get("y_source", FinanceChart.INCOME),
                x_values=request.data.get("x_values") or [],
                y_values=request.data.get("y_values") or [],
                date_from=request.data.get("date_from"),
                date_to=request.data.get("date_to"),
            )
        except FinanceError as exc:
            return error(str(exc))
        return Response(data)


# ---------------------------------------------------------------- reports
class FinanceReportViewSet(ShopScopedViewSet):
    view_permission = "finances.view.reports"
    serializer_class = FinanceReportSerializer
    queryset = FinanceReport.objects.all()
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return super().get_queryset().select_related("created_by")

    def create(self, request, *args, **kwargs):
        try:
            shop = request_shop(request, request.data)
        except FinanceError as exc:
            return error(str(exc))
        _require(shop, request.user, "finances.view.reports")
        kind = request.data.get("kind", FinanceReport.PROFIT_LOSS)
        report_format = request.data.get("format", FinanceReport.PDF)
        date_from = parse_date(str(request.data.get("date_from") or "")) or None
        date_to = parse_date(str(request.data.get("date_to") or "")) or None

        run = FinanceReport.objects.create(
            shop=shop,
            kind=kind,
            format=report_format,
            date_from=date_from,
            date_to=date_to,
            created_by=request.user,
        )

        from .tasks import generate_report

        try:
            result = generate_report.delay(run.id)
            run.task_id = result.id
            run.save(update_fields=["task_id"])
        except Exception:  # noqa: BLE001 - broker may be down, build it inline
            from .reports.builder import build_report

            try:
                build_report(run)
            except Exception as exc:  # noqa: BLE001
                run.status = FinanceReport.FAILED
                run.error = str(exc)[:240]
                run.save(update_fields=["status", "error"])

        return Response(
            FinanceReportSerializer(run).data, status=status.HTTP_201_CREATED
        )


class FinanceReportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        run = get_object_or_404(
            FinanceReport, pk=pk, shop__in=_shops_for(request.user)
        )
        _require(run.shop, request.user, "finances.reports.download")
        if not run.is_ready:
            return error("That report is not ready yet.", status.HTTP_404_NOT_FOUND)
        response = HttpResponse(run.data, content_type=run.content_type)
        response["Content-Disposition"] = f'attachment; filename="{run.filename}"'
        return response


# -------------------------------------------------------------- summaries
def _decimal_dict(data):
    converted = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            converted[key] = str(value)
        elif isinstance(value, (int, float, str, bool)) or value is None:
            converted[key] = value
        else:
            converted[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return converted


class FinanceSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            shop = request_shop(request)
        except FinanceError as exc:
            return error(str(exc), status.HTTP_404_NOT_FOUND)
        _require(shop, request.user, "finances.view.dashboard")
        date_from = parse_date(str(request.query_params.get("date_from") or "")) or None
        date_to = parse_date(str(request.query_params.get("date_to") or "")) or None
        summary = dashboard_summary(shop, date_from, date_to)
        return Response(_decimal_dict(summary))


class FinanceStatementsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            shop = request_shop(request)
        except FinanceError as exc:
            return error(str(exc), status.HTTP_404_NOT_FOUND)
        _require(shop, request.user, "finances.view.statements")

        kind = request.query_params.get("kind", "profit_loss")
        date_from = parse_date(str(request.query_params.get("date_from") or "")) or None
        date_to = parse_date(str(request.query_params.get("date_to") or "")) or None

        if kind == "trial_balance":
            data = trial_balance(shop, date_from, date_to)
        elif kind == "balance_sheet":
            data = balance_sheet(shop, date_from, date_to)
        elif kind == "cash_flow":
            data = cash_flow(shop, date_from, date_to)
        elif kind == "general_ledger":
            ledger = general_ledger(shop, date_from, date_to)
            rows = []
            for entry in ledger["rows"]:
                rows.append(
                    {
                        "id": entry.id,
                        "reference": entry.reference,
                        "occurred_at": entry.occurred_at.isoformat(),
                        "description": entry.description,
                        "amount": str(entry.amount),
                        "lines": [
                            {
                                "account": f"{line.account.code} {line.account.name}",
                                "debit": str(line.debit),
                                "credit": str(line.credit),
                            }
                            for line in entry.lines.all()
                        ],
                    }
                )
            data = {
                "kind": "general_ledger",
                "title": "General ledger",
                "start": ledger["start"],
                "end": ledger["end"],
                "rows": rows,
            }
        else:
            data = profit_and_loss(shop, date_from, date_to)

        def convert(value):
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, list):
                return [convert(item) for item in value]
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return value

        return Response(convert(data))
