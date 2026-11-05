"""URLs for SmSt Finances.

The app opens on ``/smst_finances/``. Everything below it is either a page of
the app, the API that feeds it, or a report download.
"""

from django.urls import include, path
from rest_framework import routers

from . import views
from .api import (
    FinanceAccountViewSet,
    FinanceBudgetViewSet,
    FinanceChartViewSet,
    FinanceEntryViewSet,
    FinanceOptionViewSet,
    FinanceReportDownloadView,
    FinanceReportViewSet,
    FinanceStatementsView,
    FinanceSummaryView,
)

app_name = "smst_finances"

router = routers.DefaultRouter()
router.register("accounts", FinanceAccountViewSet, basename="finance_account")
router.register("options", FinanceOptionViewSet, basename="finance_option")
router.register("entries", FinanceEntryViewSet, basename="finance_entry")
router.register("budgets", FinanceBudgetViewSet, basename="finance_budget")
router.register("charts", FinanceChartViewSet, basename="finance_chart")
router.register("reports", FinanceReportViewSet, basename="finance_report")

urlpatterns = [
    # the app
    path("", views.dashboard, name="dashboard"),
    path("entries/", views.entries, name="entries"),
    path("options/", views.options, name="options"),
    path("accounts/", views.accounts, name="accounts"),
    path("statements/", views.statements, name="statements"),
    path("charts/", views.charts, name="charts"),
    path("budgets/", views.budgets, name="budgets"),
    path("reports/", views.reports, name="reports"),
    path(
        "reports/<int:pk>/download/",
        views.report_download,
        name="report_download",
    ),
    path("receipts/", views.receipts, name="receipts"),
    path(
        "receipts/<int:pk>/print/",
        views.receipt_print,
        name="receipt_print",
    ),
    path(
        "receipts/<int:pk>/download/",
        views.receipt_download,
        name="receipt_download",
    ),
    # the API
    path("api/", include(router.urls)),
    path("api/summary/", FinanceSummaryView.as_view(), name="api_summary"),
    path("api/statements/", FinanceStatementsView.as_view(), name="api_statements"),
    path(
        "api/reports/<int:pk>/download/",
        FinanceReportDownloadView.as_view(),
        name="api_report_download",
    ),
]
