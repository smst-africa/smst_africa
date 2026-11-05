from smst_app.models import AppNotifications

class NotificationEntity():
    def any_unread_notifications(self, user_id):
        return AppNotifications.objects.filter(
            notificationUser__id=user_id,
            notificationRead=False
        ).exists()

class BaseNotifications():
    def __init__(self):
        self.repo = NotificationEntity()
    
class AnyUnreadNotifications(BaseNotifications):
    def execute(self, user):
        return self.repo.any_unread_notifications(user)

def any_unread_notifications(user):
    return AnyUnreadNotifications().execute(user)