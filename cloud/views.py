from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from .serializer import *
# Create your views here.
from rest_framework.permissions import IsAuthenticated,IsAuthenticatedOrReadOnly
from backend.models import SmstUser
from rest_framework.response import Response
from smst_app.models.smst_stock import SmstStockProduct
from smst_app.models.image import Image
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from rest_framework.decorators import action
from rest_framework import status
import logging
from rest_framework.pagination import PageNumberPagination
logger = logging.getLogger('smst')
class SmstUser(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class Notification(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "notificationId" 
    def get(self, request):
        notifications = AppNotifications.objects.filter(notificationUser=request.user)
        paginator = PageNumberPagination()
        paginator.page_size = 20
        paginated_notifications = paginator.paginate_queryset(
            notifications,
            request
        )
        serializer = AppNotificationSerializer(paginated_notifications, many=True)
        return paginator.get_paginated_response(serializer.data)

class ReadNotification(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request,notificationId):
        updated = AppNotifications.objects.filter(
            notificationId=notificationId
        ).update(notificationRead=True)
        if not updated:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response({'notificationRead': True}, status=status.HTTP_200_OK)
    
class ProductViewSet(ModelViewSet):
    queryset = SmstStockProduct.objects.all()
    serializer_class= ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    
    def list(self, request):
        products = SmstStockProduct.objects.filter(product_creator=request.user)
        serializer = ProductSerializer(products, many=True)
        
        data = serializer.data
        logger.debug(f'This is the request data {data}')
        
        for product in data:
            image_url = Image.objects.filter(id=product['product_image']).first().image_file.url
            product['product_image'] = image_url
        
        return Response(data)
        
        
    
    @transaction.atomic
    def perform_create(self, serializer):
        image_file = self.request.FILES['product_image']
        
        image = Image.objects.create(
            image_file=image_file
        )
        serializer.save(
            product_image=image,
            product_creator=self.request.user
            )
        
        
        
