"""Serializers for the SmSt Stocks API."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Order, Product, ReportRun, ShareLink, Shop, StockMovement

UserModel = get_user_model()


class ShopSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)
    stock_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    share_url = serializers.CharField(read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "slug",
            "tagline",
            "phone",
            "email",
            "address",
            "currency",
            "is_public",
            "share_token",
            "share_url",
            "product_count",
            "stock_value",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "share_token", "share_url", "created_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Give the shop a name.")
        return value.strip()


class ProductSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source="stock_state", read_only=True)
    margin = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )
    margin_value = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    stock_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    share_url = serializers.CharField(read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "shop",
            "shop_name",
            "name",
            "slug",
            "sku",
            "description",
            "attributes",
            "image",
            "buying_price",
            "selling_price",
            "quantity",
            "reorder_level",
            "unit",
            "category",
            "is_published",
            "share_token",
            "share_url",
            "state",
            "margin",
            "margin_value",
            "stock_value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "share_token",
            "share_url",
            "state",
            "margin",
            "margin_value",
            "stock_value",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Give the item a name.")
        return value.strip()

    def validate_attributes(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Attributes are pairs, such as Weight and 500g."
            )
        return {str(key): str(item) for key, item in value.items()}

    def validate(self, attrs):
        buying = attrs.get("buying_price")
        selling = attrs.get("selling_price")
        if buying is None:
            buying = getattr(self.instance, "buying_price", None)
        if selling is None:
            selling = getattr(self.instance, "selling_price", None)
        if buying is not None and selling is not None and selling < buying:
            raise serializers.ValidationError(
                {
                    "selling_price": "The selling price cannot sit below the buying price."
                }
            )
        return attrs

    
    

class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "product",
            "product_name",
            "kind",
            "kind_label",
            "quantity",
            "unit_cost",
            "note",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "product_name",
            "kind_label",
            "created_by",
            "created_by_name",
            "created_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return ""
        return obj.created_by.get_full_name() or obj.created_by.username
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get('request')

        if request:
            fields = request.query_params.get('fields')

            if fields:
                allowed_fields = {
                    "id",
                    "product",
                    "product_name",
                    "kind",
                    "kind_label",
                    "quantity",
                    "unit_cost",
                    "note",
                    "created_by",
                    "created_by_name",
                    "created_at",
                }

                requested = {
                    field.strip()
                    for field in fields.split(',')
                }

                requested &= allowed_fields

                for field in set(self.fields) - requested:
                    self.fields.pop(field)
                    
    


class OrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_image = serializers.CharField(source="product.image.url", read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "reference",
            "shop",
            "product",
            "product_name",
            "product_image",
            "quantity",
            "total",
            "customer_name",
            "customer_phone",
            "customer_email",
            "note",
            "status",
            "status_label",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "shop",
            "product_name",
            "product_image",
            "total",
            "status_label",
            "created_at",
        ]


class ShareLinkSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    target_url = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShareLink
        fields = [
            "id",
            "token",
            "shop",
            "product",
            "product_name",
            "is_active",
            "is_open",
            "expires_at",
            "views",
            "target_url",
            "created_at",
        ]
        read_only_fields = ["id", "token", "views", "target_url", "created_at"]

    def get_target_url(self, obj):
        return obj.target_path()


class ReportRunSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    format_label = serializers.CharField(source="get_format_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ReportRun
        fields = [
            "id",
            "shop",
            "kind",
            "kind_label",
            "format",
            "format_label",
            "status",
            "status_label",
            "error",
            "download_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        if not obj.is_ready:
            return None
        return f"/smst_stocks/reports/{obj.id}/download/"


class PublicProductSerializer(serializers.ModelSerializer):
    """What a customer is allowed to see on a shared page."""

    state = serializers.CharField(source="stock_state", read_only=True)
    available_quantity = serializers.SerializerMethodField()
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    shop_phone = serializers.CharField(source="shop.phone", read_only=True)
    attributes = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "attributes",
            "image",
            "selling_price",
            "buying_price",
            "unit",
            "category",
            "state",
            "available_quantity",
            "shop_name",
            "shop_phone",
        ]

    def get_available_quantity(self, obj):
        if not obj.is_available:
            return 0
        return float(obj.quantity)

    def get_attributes(self, obj):
        return dict(obj.attribute_lines())


class PublicShopSerializer(serializers.ModelSerializer):
    products = serializers.SerializerMethodField()
    currency = serializers.CharField(read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "tagline",
            "address",
            "phone",
            "currency",
            "products",
        ]

    def get_products(self, obj):
        products = obj.products.filter(is_published=True)
        return PublicProductSerializer(products, many=True).data
