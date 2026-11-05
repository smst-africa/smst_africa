from django.db import models
from django.contrib.auth import get_user_model
from core.utils import generate_notification_id
UserModel = get_user_model()
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


# Create your models here.
class AppNotifications(models.Model):
    notificationId = models.CharField(max_length=36, default=generate_notification_id, unique=True, db_index=True)
    notificationTitle = models.CharField(max_length=255)
    notificationContent = models.TextField()
    notificationUser = models.ForeignKey(UserModel, on_delete=models.CASCADE)
    notificationTime = models.DateTimeField(auto_now_add=True)
    notificationRead = models.BooleanField(default=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveBigIntegerField(default=1, null=True)
    content_object = GenericForeignKey("content_type", "object_id")
    def __str__(self):
        return f"{self.notificationTitle} {self.notificationTime}"
    
    class Meta:
        ordering = ['-notificationTime']
    