from django.urls import path, include
from rest_framework import routers
from .views import *
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
router = routers.DefaultRouter()
router.register(r'stock_products', ProductViewSet,basename='product')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('rest_framework.urls')),
    path('smst_user/', SmstUser.as_view(), name="smst_user"),
    path('notifications/', Notification.as_view(), name="notification"),
    path('notifications/<str:notificationId>/read_notification/', ReadNotification.as_view(), name="notification"),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]