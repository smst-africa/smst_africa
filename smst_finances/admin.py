from django.contrib import admin

from .models import (
    FinanceAccount,
    FinanceBudget,
    FinanceChart,
    FinanceEntry,
    FinanceOption,
    FinanceReport,
    JournalLine,
)


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ("account", "debit", "credit", "description")


@admin.register(FinanceAccount)
class FinanceAccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "type", "shop", "is_system", "is_active")
    list_filter = ("type", "is_system", "is_active")
    search_fields = ("code", "name", "shop__name")


@admin.register(FinanceOption)
class FinanceOptionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "rate_type", "rate", "applies_to", "shop", "is_active")
    list_filter = ("kind", "rate_type", "applies_to", "is_active")
    search_fields = ("name", "shop__name")


@admin.register(FinanceEntry)
class FinanceEntryAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "description",
        "kind",
        "amount",
        "shop",
        "status",
        "occurred_at",
    )
    list_filter = ("kind", "status", "source")
    search_fields = ("reference", "description", "note", "shop__name")
    date_hierarchy = "occurred_at"
    inlines = [JournalLineInline]


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ("entry", "account", "debit", "credit")
    list_filter = ("account__type",)
    search_fields = ("entry__reference", "account__name")


@admin.register(FinanceBudget)
class FinanceBudgetAdmin(admin.ModelAdmin):
    list_display = ("name", "period", "amount", "shop", "starts_on", "ends_on")
    list_filter = ("period",)
    search_fields = ("name", "shop__name")


@admin.register(FinanceChart)
class FinanceChartAdmin(admin.ModelAdmin):
    list_display = ("title", "chart_type", "x_source", "y_source", "shop")
    list_filter = ("chart_type", "x_source", "y_source")
    search_fields = ("title", "shop__name")


@admin.register(FinanceReport)
class FinanceReportAdmin(admin.ModelAdmin):
    list_display = ("kind", "format", "status", "shop", "created_at")
    list_filter = ("kind", "format", "status")
    search_fields = ("shop__name",)
