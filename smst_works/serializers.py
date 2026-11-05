"""Serializers for the SmSt Works API."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from smst_stocks.models import Product, Shop, StockMovement

from .models import (
    ALL_PERMISSIONS,
    Customer,
    Employee,
    Guide,
    Job,
    JobInput,
    JobOutput,
    LoyaltyTransaction,
    Rank,
    Supplier,
)


class RankSerializer(serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()
    permission_labels = serializers.SerializerMethodField()

    class Meta:
        model = Rank
        fields = [
            "id",
            "shop",
            "name",
            "description",
            "permissions",
            "permission_labels",
            "is_default",
            "employee_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "shop", "is_default", "created_at", "updated_at"]

    def get_employee_count(self, rank) -> int:
        return rank.employees.count()

    def get_permission_labels(self, rank):
        return rank.permission_labels

    def validate_permissions(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("Permissions must be a list.")
        clean = []
        for key in value:
            if key not in ALL_PERMISSIONS:
                raise serializers.ValidationError(f"Unknown permission “{key}”.")
            if key not in clean:
                clean.append(key)
        return clean

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the rank a name.")
        return value


class EmployeeSerializer(serializers.ModelSerializer):
    rank_name = serializers.CharField(source="rank.name", read_only=True, default="")
    status_label = serializers.CharField(
        source="get_status_display", read_only=True
    )
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id",
            "shop",
            "user",
            "name",
            "phone",
            "email",
            "role",
            "rank",
            "rank_name",
            "permissions",
            "status",
            "status_label",
            "hired_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "shop", "user", "created_at", "updated_at"]

    def get_permissions(self, employee):
        return sorted(employee.permissions)

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the employee a name.")
        return value


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = LoyaltyTransaction
        fields = [
            "id",
            "kind",
            "kind_label",
            "points",
            "reason",
            "created_at",
        ]
        read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
    tier = serializers.CharField(read_only=True)
    loyalty_count = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "shop",
            "name",
            "phone",
            "email",
            "notes",
            "points",
            "tier",
            "loyalty_count",
            "joined_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "shop",
            "points",
            "tier",
            "loyalty_count",
            "joined_at",
            "updated_at",
        ]

    def get_loyalty_count(self, customer) -> int:
        return customer.loyalty_transactions.count()

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the customer a name.")
        return value


class SupplierSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), many=True, required=False
    )
    product_names = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id",
            "shop",
            "name",
            "contact_name",
            "phone",
            "email",
            "address",
            "notes",
            "products",
            "product_names",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "shop", "created_at", "updated_at"]

    def get_product_names(self, supplier):
        return [product.name for product in supplier.products.all()]

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the supplier a name.")
        return value


class GuideSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(
        source="updated_by.username", read_only=True, default=""
    )

    class Meta:
        model = Guide
        fields = [
            "id",
            "shop",
            "title",
            "category",
            "body",
            "is_published",
            "position",
            "updated_by",
            "updated_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "shop",
            "updated_by",
            "created_at",
            "updated_at",
        ]

    def validate_title(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the guide a title.")
        return value

    def validate_body(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Write the guide, even one line.")
        return value


class JobInputSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)

    class Meta:
        model = JobInput
        fields = ["id", "product", "product_name", "unit", "quantity", "note"]


class JobOutputSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)

    class Meta:
        model = JobOutput
        fields = ["id", "product", "product_name", "unit", "quantity", "note"]


class JobSerializer(serializers.ModelSerializer):
    inputs = JobInputSerializer(many=True, read_only=True)
    outputs = JobOutputSerializer(many=True, read_only=True)
    status_label = serializers.CharField(
        source="get_status_display", read_only=True
    )
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True, default=""
    )
    waiting_seconds = serializers.FloatField(read_only=True)
    elapsed_seconds = serializers.FloatField(read_only=True)
    duration_seconds = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "shop",
            "title",
            "description",
            "status",
            "status_label",
            "created_by",
            "created_by_name",
            "started_at",
            "finished_at",
            "note",
            "inputs",
            "outputs",
            "waiting_seconds",
            "elapsed_seconds",
            "duration_seconds",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class JobLineWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    note = serializers.CharField(required=False, allow_blank=True)


class JobCreateSerializer(serializers.Serializer):
    shop = serializers.PrimaryKeyRelatedField(
        queryset=Shop.objects.all(), required=False
    )
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True)
    inputs = JobLineWriteSerializer(many=True, required=False)
    outputs = JobLineWriteSerializer(many=True, required=False)


class ShopMovementSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    kind = serializers.ChoiceField(choices=StockMovement.KIND_CHOICES)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True)


class PointsSerializer(serializers.Serializer):
    points = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True)
