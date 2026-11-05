"""URLs for SmSt Works.

The app opens on ``/smst_works/``. Everything below it is either a page, the
API that feeds it, or the live timeline.
"""

from django.urls import include, path
from rest_framework import routers

from . import views
from .api import (
    CustomerViewSet,
    EmployeeViewSet,
    GuideViewSet,
    JobViewSet,
    RankViewSet,
    ShopMovementView,
    SummaryView,
    SupplierViewSet,
    TimelineView,
)

app_name = "smst_works"

router = routers.DefaultRouter()
router.register("ranks", RankViewSet, basename="rank")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("customers", CustomerViewSet, basename="customer")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("guides", GuideViewSet, basename="guide")
router.register("jobs", JobViewSet, basename="job")

urlpatterns = [
    # the app
    path("", views.dashboard, name="dashboard"),
    path("jobs/", views.jobs, name="jobs"),
    path("employees/", views.employees, name="employees"),
    path("ranks/", views.ranks, name="ranks"),
    path("customers/", views.customers, name="customers"),
    path("suppliers/", views.suppliers, name="suppliers"),
    path("guides/", views.guides, name="guides"),
    # the API
    path("api/", include(router.urls)),
    path("api/timeline/", TimelineView.as_view(), name="timeline"),
    path("api/summary/", SummaryView.as_view(), name="summary"),
    path(
        "api/shop/movement/",
        ShopMovementView.as_view(),
        name="shop_movement",
    ),
]
