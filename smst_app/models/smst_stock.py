from django.db import models
from django.contrib.auth import get_user_model
from .image import Image
UserModel = get_user_model()
from django.db import transaction
import logging
logger = logging.getLogger('smst')
from django.utils.translation import gettext_lazy as _
import cloudinary.uploader
from django.db import transaction
def get_deleted_user():
    return UserModel.objects.get(username='deleted_user')

class SmstStockProduct(models.Model):
    product_name = models.CharField(max_length=255)
    product_description = models.JSONField(default=dict)
    product_image = models.ForeignKey(Image, on_delete=models.PROTECT)
    product_creator = models.ForeignKey(UserModel, on_delete=models.SET(get_deleted_user))
    
    
    def save(self, *args, **kwargs):
        from core.tasks import save_notification
        super().save(*args, **kwargs)
        save_notification.delay(_('Stock Updated'), _('Product {product_name} has been created').format(product_name=self.product_name), self.product_creator.username, self.__class__.__name__, self.id)
    
    
    @transaction.atomic
    def delete(self, *args, **kwargs):
        from core.tasks import save_notification
        
        if self.product_image.image_file.public_id:
            cloudinary.uploader.destroy(
                self.product_image.image_file.public_id,
                invalidate=True
            )
            
        super().delete(*args, **kwargs)
        save_notification.delay(_('Stock Deleted'), _('Product {product_name} has been deleted').format(product_name=self.product_name), self.product_creator.username, self.__class__.__name__, self.id)
        
                
        