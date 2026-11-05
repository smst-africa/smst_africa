"""The API behind SmSt Stocks.

Everything the app does goes through these endpoints: reading and writing
products, recording movements, taking orders and building reports. The public
endpoints are open so that a customer can use a shared link without an
account.
"""

import logging

from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, Product, ReportRun, ShareLink, Shop, StockMovement
from . import finance_bridge
from .serializers import (
    OrderSerializer,
    ProductSerializer,
    PublicProductSerializer,
    PublicShopSerializer,
    ReportRunSerializer,
    ShareLinkSerializer,
    ShopSerializer,
    StockMovementSerializer,
)
from .services import (
    StockError,
    check_item_limit,
    check_shop_limit,
    create_order,
    create_share_link,
    record_delivery,
    record_movement,
    shop_summary,
    update_order_status,
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


STOCK_VIEWS = (
    "stocks.view",
    "stocks.view.products",
    "stocks.view.movements",
    "stocks.view.low_stock",
    "stocks.view.orders",
    "stocks.view.reports",
    "stocks.view.links",
    "stocks.view.shops",
)


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


def _visible_movements(queryset, shop, user):
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


def _movement_permission(kind):
    return (
        "stocks.add"
        if kind in (StockMovement.DELIVERY, StockMovement.OPENING)
        else "stocks.move"
    )


def _money_account(request):
    """The finance account the money moved through, chosen on the form.

    Only asset accounts (cash, bank, receivables, stock) can settle a stock
    movement. An empty answer means the movement stays in stock only.
    """
    value = request.data.get("account")
    if value in (None, ""):
        return None
    finance_models = finance_bridge.models()

    account = finance_models.FinanceAccount.objects.filter(
        pk=value,
        shop__in=_shops_for(request.user),
        type=finance_models.FinanceAccount.ASSET,
    ).first()
    if not account:
        raise StockError("Choose an asset account of this shop to save the money in.")
    return account


def _finance_payload(movement):
    """The entry a movement produced, if SmSt Finances is ready."""
    try:
        finance = finance_bridge.services()
    except Exception:  # noqa: BLE001 - finances may not be installed
        return None
    try:
        return finance.movement_finance_payload(movement)
    except Exception:  # noqa: BLE001 - a missing table must not break the API
        return None


class ShopViewSet(viewsets.ModelViewSet):
    """The shops belonging to the signed in user."""

    serializer_class = ShopSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop and not any(
            _can(shop, self.request.user, key) for key in STOCK_VIEWS
        ):
            raise PermissionDenied("Your rank does not open the stock app.")
        return (
            _shops_for(self.request.user)
            .annotate(product_count=Count("products"))
            .order_by("name")
        )

    def perform_create(self, serializer):
        check_shop_limit(self.request.user)
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        shop = self.get_object()
        if shop.owner_id != self.request.user.id:
            raise PermissionDenied("That shop is not yours.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied("Only the owner can remove the shop.")
        instance.delete()

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        shop = self.get_object()
        _require(shop, request.user, "stocks.view")
        data = shop_summary(shop)
        data["stock_value"] = str(data["stock_value"])
        data["buying_value"] = str(data["buying_value"])
        data["margin_value"] = str(data["margin_value"])
        data["units"] = str(data["units"])
        data["low_stock"] = ProductSerializer(
            data["low_stock"], many=True
        ).data
        return Response(data)


class ProductViewSet(viewsets.ModelViewSet):
    """Products, and the actions that change a shop's stock."""

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop:
            _require(shop, self.request.user, "stocks.view.products")
        queryset = (
            Product.objects.filter(shop=shop) if shop else Product.objects.none()
        ).select_related("shop").order_by("name")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        state = self.request.query_params.get("state")
        if state == "low":
            queryset = queryset.filter(
                Q(quantity__lte=0)
                | Q(reorder_level__gt=0, quantity__lte=F("reorder_level"))
            )
        elif state == "out":
            queryset = queryset.filter(quantity__lte=0)
        return queryset

    def perform_create(self, serializer):
        shop = serializer.validated_data.get("shop")
        if not shop or not _shops_for(self.request.user).filter(pk=shop.pk).exists():
            raise PermissionDenied("Choose a shop you can work in.")
        _require(shop, self.request.user, "stocks.add")
        check_item_limit(shop)
        serializer.save()

    def perform_update(self, serializer):
        product = self.get_object()
        shop = serializer.validated_data.get("shop", product.shop)
        if not _shops_for(self.request.user).filter(pk=shop.pk).exists():
            raise PermissionDenied("That shop is not yours.")
        _require(shop, self.request.user, "stocks.add")
        serializer.save()

    def perform_destroy(self, instance):
        _require(instance.shop, self.request.user, "stocks.add")
        instance.delete()

    @action(detail=True, methods=["post"])
    def movement(self, request, pk=None):
        """Record a movement against a product."""
        product = self.get_object()
        kind = request.data.get("kind", StockMovement.ADJUSTMENT)
        _require(product.shop, request.user, _movement_permission(kind))
        try:
            quantity = request.data.get("quantity", 0)
            account = _money_account(request)
            movement = record_movement(
                product,
                kind,
                quantity,
                note=request.data.get("note", ""),
                unit_cost=request.data.get("unit_cost"),
                user=request.user,
                account=account,
            )
        except StockError as exc:
            return error(str(exc))
        except ValueError:
            return error("Enter how many items moved.")

        return Response(
            {
                "product": ProductSerializer(product).data,
                "movement": StockMovementSerializer(movement).data,
                "finance": _finance_payload(movement),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Show this product on the shared page, or take it off."""
        product = self.get_object()
        _require(product.shop, request.user, "stocks.add")
        product.is_published = bool(request.data.get("is_published", True))
        product.save(update_fields=["is_published", "updated_at"])
        from .realtime import broadcast_product

        broadcast_product(product, event="product.published")
        return Response(ProductSerializer(product).data)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Create a link to the shared page for this product."""
        product = self.get_object()
        _require(product.shop, request.user, "stocks.add")
        link = create_share_link(product.shop, product=product)
        return Response(
            ShareLinkSerializer(link).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """The items that need ordering before they run out."""
        shop = self._shop_from_request()
        if shop is None:
            return error("Choose a shop.")
        _require(shop, request.user, "stocks.view.low_stock")
        products = shop.products.filter(
            Q(quantity__lte=0)
            | Q(reorder_level__gt=0, quantity__lte=F("reorder_level"))
        ).order_by("quantity", "name")
        return Response(ProductSerializer(products, many=True).data)

    @action(detail=False, methods=["post"])
    def delivery(self, request):
        """Record a delivery with several lines."""
        shop = self._shop_from_request()
        if shop is None:
            return error("Choose a shop.")
        _require(shop, request.user, "stocks.add")
        lines = request.data.get("lines") or []
        try:
            account = _money_account(request)
            movements = record_delivery(
                shop,
                lines,
                note=request.data.get("note", ""),
                user=request.user,
                account=account,
            )
        except StockError as exc:
            return error(str(exc))
        except ValueError:
            return error("Enter how many items arrived.")

        return Response(
            {
                "movements": StockMovementSerializer(movements, many=True).data,
                "products": ProductSerializer(
                    shop.products.order_by("name"), many=True
                ).data,
                "finance": [_finance_payload(movement) for movement in movements],
            },
            status=status.HTTP_201_CREATED,
        )

    def _shop_from_request(self):
        shop_id = self.request.query_params.get("shop") or self.request.data.get(
            "shop"
        )
        if not shop_id:
            return None
        return _shops_for(self.request.user).filter(pk=shop_id).first()


class StockMovementViewSet(viewsets.ModelViewSet):
    """The ledger. Movements are written through the service layer."""

    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop:
            _require(shop, self.request.user, "stocks.view.movements")
        queryset = (
            StockMovement.objects.filter(product__shop=shop)
            if shop
            else StockMovement.objects.none()
        ).select_related("product", "created_by")
        product = self.request.query_params.get("product")
        if product:
            queryset = queryset.filter(product_id=product)
        return _visible_movements(queryset, shop, self.request.user)

    def create(self, request, *args, **kwargs):
        product_id = request.data.get("product")
        product = get_object_or_404(
            Product, pk=product_id, shop__in=_shops_for(request.user)
        )
        kind = request.data.get("kind", StockMovement.ADJUSTMENT)
        _require(product.shop, request.user, _movement_permission(kind))
        try:
            quantity = request.data.get("quantity", 0)
            account = _money_account(request)
            movement = record_movement(
                product,
                kind,
                quantity,
                note=request.data.get("note", ""),
                unit_cost=request.data.get("unit_cost"),
                user=request.user,
                account=account,
            )
        except StockError as exc:
            return error(str(exc))
        except ValueError:
            return error("Enter how many items moved.")

        return Response(
            {
                **StockMovementSerializer(movement).data,
                "finance": _finance_payload(movement),
            },
            status=status.HTTP_201_CREATED,
        )
    
    def paginate_queryset(self, queryset):
        if self.request.query_params.get('paginate') == 'false':
            return None

        return super().paginate_queryset(queryset)


class OrderViewSet(viewsets.ModelViewSet):
    """Orders placed through a shared page."""

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop:
            _require(shop, self.request.user, "stocks.view.orders")
        queryset = (
            Order.objects.filter(shop=shop) if shop else Order.objects.none()
        ).select_related("product", "shop")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def create(self, request, *args, **kwargs):
        product = get_object_or_404(
            Product, pk=request.data.get("product"), shop__in=_shops_for(request.user)
        )
        _require(product.shop, request.user, "stocks.move")
        try:
            order = create_order(
                product,
                request.data.get("quantity", 1),
                request.data.get("customer_name", ""),
                request.data.get("customer_phone", ""),
                request.data.get("customer_email", ""),
                request.data.get("note", ""),
            )
        except StockError as exc:
            return error(str(exc))
        except ValueError:
            return error("Enter the details of the order.")

        from .tasks import notify_new_order

        notify_new_order.delay(order.id)

        return Response(
            OrderSerializer(order).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        from .services import cancel_order

        order = self.get_object()
        _require(order.shop, request.user, "stocks.move")
        try:
            cancel_order(order)
        except StockError as exc:
            return error(str(exc))
        return Response(OrderSerializer(order).data)


class ShareLinkViewSet(viewsets.ModelViewSet):
    """Links that can be switched off or given an end date."""

    serializer_class = ShareLinkSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop:
            _require(shop, self.request.user, "stocks.view.links")
        return (
            ShareLink.objects.filter(shop=shop) if shop else ShareLink.objects.none()
        )

    def perform_create(self, serializer):
        shop = serializer.validated_data.get("shop")
        if not shop or not _shops_for(self.request.user).filter(pk=shop.pk).exists():
            raise PermissionDenied("Choose a shop you can work in.")
        _require(shop, self.request.user, "stocks.add")
        serializer.save()

    def perform_update(self, serializer):
        _require(serializer.instance.shop, self.request.user, "stocks.add")
        serializer.save()

    def perform_destroy(self, instance):
        _require(instance.shop, self.request.user, "stocks.add")
        instance.delete()


class ReportRunViewSet(viewsets.ModelViewSet):
    """Reports, and the file they produced."""

    serializer_class = ReportRunSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        shop = _shop_for_request(self.request)
        if shop:
            _require(shop, self.request.user, "stocks.view.reports")
        return (
            ReportRun.objects.filter(shop=shop) if shop else ReportRun.objects.none()
        )

    def create(self, request, *args, **kwargs):
        shop = get_object_or_404(_shops_for(request.user), pk=request.data.get("shop"))
        _require(shop, request.user, "stocks.view.reports")
        kind = request.data.get("kind", ReportRun.STOCK)
        report_format = request.data.get("format", ReportRun.PDF)

        run = ReportRun.objects.create(
            shop=shop,
            kind=kind,
            format=report_format,
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
                run.status = ReportRun.FAILED
                run.error = str(exc)[:240]
                run.save(update_fields=["status", "error"])

        return Response(
            ReportRunSerializer(run).data, status=status.HTTP_201_CREATED
        )


# ----------------------------------------------------------------- public
class PublicProductView(APIView):
    """A product on its shared page, with what is in stock right now."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        product = (
            Product.objects.select_related("shop")
            .filter(share_token=token, is_published=True)
            .first()
        )
        if not product:
            return error("That page is not available.", status.HTTP_404_NOT_FOUND)
        return Response(PublicProductSerializer(product).data)


class PublicShopView(APIView):
    """The catalogue a shop shares."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        shop = Shop.objects.filter(share_token=token, is_public=True).first()
        if not shop:
            return error("That page is not available.", status.HTTP_404_NOT_FOUND)
        return Response(PublicShopSerializer(shop).data)


class PublicOrderView(APIView):
    """A customer asking for stock from a shared page."""

    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("product")
        product = (
            Product.objects.select_related("shop")
            .filter(share_token=token, is_published=True)
            .first()
        )
        if not product:
            return error("That item is no longer listed.", status.HTTP_404_NOT_FOUND)

        name = (request.data.get("customer_name") or "").strip()
        phone = (request.data.get("customer_phone") or "").strip()
        if not name:
            return error("Tell us your name.")
        if not phone:
            return error("Give us a phone number to reach you on.")

        try:
            order = create_order(
                product,
                request.data.get("quantity", 1),
                name,
                phone,
                (request.data.get("customer_email") or "").strip(),
                (request.data.get("note") or "").strip(),
            )
        except StockError as exc:
            return error(str(exc))
        except ValueError:
            return error("Enter how many you need.")

        from .tasks import notify_new_order

        notify_new_order.delay(order.id)

        return Response(
            {
                "reference": order.reference,
                "message": "We have your request. The shop will call you.",
                "quantity": float(order.quantity),
                "total": str(order.total),
            },
            status=status.HTTP_201_CREATED,
        )


class PublicCatalogueView(APIView):
    """Every published item across the shops that share their catalogue."""

    permission_classes = [AllowAny]

    def get(self, request):
        queryset = Product.objects.filter(is_published=True).select_related("shop")
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        shop = request.query_params.get("shop")
        if shop:
            queryset = queryset.filter(shop__share_token=shop)
        return Response(PublicProductSerializer(queryset[:60], many=True).data)


class ReportDownloadView(APIView):
    """Hands back the file a report produced."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        run = get_object_or_404(
            ReportRun, pk=pk, shop__in=_shops_for(request.user)
        )
        _require(run.shop, request.user, "stocks.reports.download")
        if not run.is_ready:
            return error("That report is not ready yet.", status.HTTP_404_NOT_FOUND)
        response = HttpResponse(run.data, content_type=run.content_type)
        response["Content-Disposition"] = f'attachment; filename="{run.filename}"'
        return response
