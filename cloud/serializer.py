from rest_framework import serializers
from smst_app.models import AppNotifications
from backend.models import SmstUser
from django.db import transaction
class AppNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppNotifications
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmstUser
        fields = ['username', 'first_name', 'last_name']

from smst_app.models.image import Image

class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = '__all__'

from smst_app.models.smst_stock import SmstStockProduct

class ProductSerializer(serializers.ModelSerializer):
    image = ImageSerializer
    creator = UserSerializer
    product_creator =  serializers.SlugRelatedField(
        read_only=True,
        slug_field='username'
    )
    
    class Meta:
        model = SmstStockProduct
        fields = '__all__'
        read_only_fields = ['product_creator', 'product_image']
    