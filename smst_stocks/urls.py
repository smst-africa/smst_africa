"""URLs for SmSt Stocks.

The app opens on ``/smst_stocks/``. Everything below it is either a page of
the app, the API that feeds it, or a public page a customer can open.
"""

from django.urls import include, path, re_path
from rest_framework import routers

from . import views
from .api import (
    OrderViewSet,
    ProductViewSet,
    PublicCatalogueView,
    PublicOrderView,
    PublicProductView,
    PublicShopView,
    ReportDownloadView,
    ReportRunViewSet,
    ShareLinkViewSet,
    ShopViewSet,
    StockMovementViewSet,
)

app_name = "smst_stocks"

router = routers.DefaultRouter()
router.register("shops", ShopViewSet, basename="stock_shop")
router.register("products", ProductViewSet, basename="stock_product")
router.register("movements", StockMovementViewSet, basename="stock_movement")
router.register("orders", OrderViewSet, basename="stock_order")
router.register("links", ShareLinkViewSet, basename="stock_link")
router.register("reports", ReportRunViewSet, basename="stock_report")

urlpatterns = [
    # the app
    path("", views.dashboard, name="dashboard"),
    path("products/", views.products, name="products"),
    path("products/new/", views.product_form, name="product_create"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", views.product_form, name="product_edit"),
    path("movements/", views.movements, name="movements"),
    path("low-stock/", views.low_stock, name="low_stock"),
    path("orders/", views.orders, name="orders"),
    path("reports/", views.reports, name="reports"),
    path("reports/<int:pk>/download/", views.report_download, name="report_download"),
    path("shops/", views.shops, name="shops"),
    path("links/", views.links, name="links"),
    # the cart
    path("cart/", views.cart, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/scan/", views.cart_scan, name="cart_scan"),
    path("cart/<int:pk>/release/", views.cart_release, name="cart_release"),
    path("cart/process/", views.cart_process_all, name="cart_process_all"),
    path("cart/<int:pk>/process/", views.cart_process, name="cart_process"),
    # public pages
    path("p/<str:token>/", views.public_product, name="public_product"),
    path("s/<str:token>/", views.public_shop, name="public_shop"),
    # the API
    path("api/", include(router.urls)),
    path(
        "api/public/products/<str:token>/",
        PublicProductView.as_view(),
        name="public_product_api",
    ),
    path(
        "api/public/shops/<str:token>/",
        PublicShopView.as_view(),
        name="public_shop_api",
    ),
    path("api/public/orders/", PublicOrderView.as_view(), name="public_order_api"),
    path(
        "api/public/catalogue/",
        PublicCatalogueView.as_view(),
        name="public_catalogue_api",
    ),
    path(
        "api/reports/<int:pk>/download/",
        ReportDownloadView.as_view(),
        name="report_download_api",
    ),
]
