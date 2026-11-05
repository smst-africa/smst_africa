"""Serializers for the SmSt Finances API."""

from rest_framework import serializers

from .models import (
    FinanceAccount,
    FinanceBudget,
    FinanceChart,
    FinanceEntry,
    FinanceOption,
    FinanceReport,
    JournalLine,
)
from .services import budget_status


class FinanceAccountSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    balance = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    normal_balance = serializers.CharField(read_only=True)

    class Meta:
        model = FinanceAccount
        fields = [
            "id",
            "shop",
            "code",
            "name",
            "type",
            "type_label",
            "description",
            "is_system",
            "is_active",
            "normal_balance",
            "balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_system", "balance", "created_at", "updated_at"]

    def validate_code(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the account a code.")
        return value

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the account a name.")
        return value


class FinanceOptionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    rate_type_label = serializers.CharField(
        source="get_rate_type_display", read_only=True
    )
    applies_to_label = serializers.CharField(
        source="get_applies_to_display", read_only=True
    )
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = FinanceOption
        fields = [
            "id",
            "shop",
            "name",
            "kind",
            "kind_label",
            "description",
            "rate_type",
            "rate_type_label",
            "rate",
            "applies_to",
            "applies_to_label",
            "account",
            "account_name",
            "is_active",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give the option a name.")
        return value

    def validate_rate(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("A rate cannot be below zero.")
        return value


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_type = serializers.CharField(source="account.type", read_only=True)

    class Meta:
        model = JournalLine
        fields = [
            "id",
            "account",
            "account_code",
            "account_name",
            "account_type",
            "description",
            "debit",
            "credit",
        ]
        read_only_fields = fields


class FinanceEntrySerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    option_name = serializers.CharField(source="option.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    movement_label = serializers.CharField(read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    payment_account_name = serializers.CharField(
        source="payment_account.name", read_only=True
    )
    lines = JournalLineSerializer(many=True, read_only=True)
    signed_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = FinanceEntry
        fields = [
            "id",
            "shop",
            "option",
            "option_name",
            "product",
            "product_name",
            "movement",
            "movement_label",
            "order",
            "account",
            "account_name",
            "payment_account",
            "payment_account_name",
            "kind",
            "kind_label",
            "status",
            "status_label",
            "source",
            "source_label",
            "reference",
            "amount",
            "signed_amount",
            "base_amount",
            "rate",
            "description",
            "note",
            "occurred_at",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "source",
            "signed_amount",
            "lines",
            "created_at",
            "updated_at",
        ]

    def validate_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("An amount cannot be below zero.")
        return value

    def validate(self, attrs):
        if attrs.get("status") == FinanceEntry.VOID:
            raise serializers.ValidationError(
                {"status": "Use the void action to void an entry."}
            )
        return attrs


class FinanceBudgetSerializer(serializers.ModelSerializer):
    period_label = serializers.CharField(source="get_period_display", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    option_name = serializers.CharField(source="option.name", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = FinanceBudget
        fields = [
            "id",
            "shop",
            "name",
            "account",
            "account_name",
            "option",
            "option_name",
            "period",
            "period_label",
            "amount",
            "starts_on",
            "ends_on",
            "notes",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_status(self, obj):
        data = budget_status(obj)
        return {
            "start": data["start"].isoformat(),
            "end": data["end"].isoformat(),
            "spent": str(data["spent"]),
            "remaining": str(data["remaining"]),
            "percent": data["percent"],
        }

    def validate_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("A budget cannot be below zero.")
        return value


class FinanceChartSerializer(serializers.ModelSerializer):
    chart_type_label = serializers.CharField(
        source="get_chart_type_display", read_only=True
    )
    x_source_label = serializers.CharField(
        source="get_x_source_display", read_only=True
    )
    y_source_label = serializers.CharField(
        source="get_y_source_display", read_only=True
    )
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FinanceChart
        fields = [
            "id",
            "shop",
            "title",
            "chart_type",
            "chart_type_label",
            "x_source",
            "x_source_label",
            "y_source",
            "y_source_label",
            "x_values",
            "y_values",
            "filters",
            "description",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return ""
        return obj.created_by.get_full_name() or obj.created_by.username

    def validate(self, attrs):
        x_values = attrs.get("x_values") or []
        y_values = attrs.get("y_values") or []
        if x_values and y_values and len(x_values) != len(y_values):
            raise serializers.ValidationError(
                {"y_values": "The X and Y values must have the same length."}
            )
        if not (attrs.get("title") or "").strip():
            raise serializers.ValidationError({"title": "Give the graph a title."})
        return attrs


class FinanceReportSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    format_label = serializers.CharField(source="get_format_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = FinanceReport
        fields = [
            "id",
            "shop",
            "kind",
            "kind_label",
            "format",
            "format_label",
            "status",
            "status_label",
            "date_from",
            "date_to",
            "error",
            "download_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        if not obj.is_ready:
            return None
        return f"/smst_finances/reports/{obj.id}/download/"
