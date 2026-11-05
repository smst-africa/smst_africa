from django.contrib import admin

from .models import (
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


class JobInputInline(admin.TabularInline):
    model = JobInput
    extra = 0


class JobOutputInline(admin.TabularInline):
    model = JobOutput
    extra = 0


@admin.register(Rank)
class RankAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "is_default", "employee_count")
    list_filter = ("is_default", "shop")
    search_fields = ("name", "shop__name")

    @admin.display(description="Employees")
    def employee_count(self, rank):
        return rank.employees.count()


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "rank", "status", "hired_at")
    list_filter = ("status", "rank", "shop")
    search_fields = ("name", "phone", "email", "user__username")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "points", "tier", "joined_at")
    list_filter = ("shop",)
    search_fields = ("name", "phone", "email")


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = ("customer", "kind", "points", "reason", "created_at")
    list_filter = ("kind",)
    search_fields = ("customer__name", "reason")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "contact_name", "phone")
    list_filter = ("shop",)
    search_fields = ("name", "contact_name", "phone", "email")
    filter_horizontal = ("products",)


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ("title", "shop", "category", "is_published", "position")
    list_filter = ("is_published", "shop", "category")
    search_fields = ("title", "body")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "shop", "status", "started_at", "finished_at")
    list_filter = ("status", "shop")
    search_fields = ("title", "description")
    inlines = [JobInputInline, JobOutputInline]
