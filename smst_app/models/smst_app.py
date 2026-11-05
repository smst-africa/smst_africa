from django.db import models

class SmstApp(models.Model):
    smst_app = models.CharField(max_length=255)
    