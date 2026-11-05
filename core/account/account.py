from dataclasses import dataclass
from backend.models import *
from backend.models import SmstUserPushSubscription as PushModel
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
import logging
from django.utils.translation import gettext as _



logger = logging.getLogger('smst')

@dataclass
class Account:
    username: str
    account_id: int | None = None
    email: str | None = None

@dataclass
class PushSub:
    endpoint: str
    p256dh: str
    auth: str
    user: int    

class AccountRepository:
    def check_username(self, account:Account)->str:
        user = SmstUser.objects.filter(username=account.username)
        if user:
            return "exists"
        return "valid"
    
    def check_notification(self, user,endpoint):
        return SmstUserPushSubscription.objects.filter(user=user, endpoint=endpoint).exists()
    
    def check_password(self, user_id, password):
        user = SmstUser.objects.filter(id=user_id).first()
        return check_password(password, user.password)
    @transaction.atomic
    def change_username(self, account:Account)->bool:
        try:
            from core.tasks import send_notification
            SmstUser.objects.filter(id=account.account_id).update(username=account.username)
            send_notification.delay(account.username, _('Username Changed.'),_(f'You have changed your username recently.'), 'https://user.smst.africa/accounts/profile/?view_page=security')
            return True
        except:
            return False
    
    @transaction.atomic
    def create_account(self, email, password)->bool:
        try:
            SmstUser.objects.get_or_create(
                email= email,
                defaults={
                    "password": make_password(password),
                    'first_name': email.split("@")[0],
                    'social_acc': False
                }
            )
            return True
        except:
            return False
    
    @transaction.atomic
    def change_password(self, email, password)->bool:
        try:
            from core.tasks import send_notification
           
            user=SmstUser.objects.filter(email=email)
            user.update(password=make_password(password))
            send_notification.delay(user.first().username,_('Password Changed.'),_(f'You have changed your password'), 'https://user.smst.africa/accounts/profile/?view_page=account')

            return True
        except:
            return False
    
    @transaction.atomic
    def enable_notifications(self, pushSub:PushSub)->bool:
        from core.tasks import send_notification
        try:
            user = SmstUser.objects.get(id=pushSub.user)
            PushModel.objects.update_or_create(
                endpoint=pushSub.endpoint,
                defaults={
                    'user': user,
                    'p256dh': pushSub.p256dh,
                    'auth': pushSub.auth
                }
            )
            send_notification.delay(user.username, _('Notification'), _('Here is a message'), pro=user.has_active_subscription)
            return True
        except Exception as e:
            logger.critical(f'PushSub Model Error {e}')
            return False
    
    @transaction.atomic
    def silence_notifications(self, endpoint, user):
        notifications= PushModel.objects.filter(
            endpoint=endpoint,
            user__id=user
        ).first()
        if notifications:
            notifications.delete()
            return True
        return False
    @transaction.atomic
    def change_personal_info(self, user_id, info_field, new_value):
        try:
            user = SmstUser.objects.get(id=user_id)
            setattr(user, info_field, new_value)
            user.save()
            return True
        except:
            return False
    
    @transaction.atomic
    def remove_notifications(self, user):
        PushModel.objects.filter(user__username=user).delete()
    
class BaseAccount:
    def __init__(self):
        self.repo = AccountRepository()

class CheckUsername(BaseAccount):
    def execute(self, username):
        account = Account(username=username)
        return self.repo.check_username(account)

def check_username(username):
    return CheckUsername().execute(username)

class ChangeUsername(BaseAccount):
    def execute(self, username, user_id):
        account = Account(username=username, account_id=user_id)
        return self.repo.change_username(account)

def change_username(new_username, user_id):
    return ChangeUsername().execute(new_username, user_id)

class CreateAccount(BaseAccount):
    def execute(self, email, password):
        return self.repo.create_account(email, password)

def create_account(email, passsword):
    return CreateAccount().execute(email, passsword)

class ChangePassword(BaseAccount):
    def execute(self, email, new_password):
        return self.repo.change_password(email, new_password)

def change_password(email, new_password):
    return ChangePassword().execute(email, new_password)

class EnableNotifications(BaseAccount):
    def execute(self, endpoint, p256dh, auth, user):
        pushSub = PushSub(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user=user
        )
        return self.repo.enable_notifications(pushSub)
    
def enable_notifications(endpoint, p256dh, auth, user):
    return EnableNotifications().execute(endpoint, p256dh, auth, user)

class SilenceNotifications(BaseAccount):
    def execute(self, endpoint, user):
        return self.repo.silence_notifications(endpoint, user)
    
def silence_notifications(endpoint, user):
    return SilenceNotifications().execute(endpoint, user)

class RemoveNotifications(BaseAccount):
    def execute(self, user):
        return self.repo.remove_notifications(user)
    
def remove_notifications(user):
    return RemoveNotifications().execute(user)

class CheckNotification(BaseAccount):
    def execute(self, user, endpoint):
        return self.repo.check_notification(user, endpoint)
    
def check_notification(user, endpoint):
    return CheckNotification().execute(user, endpoint)

class ChangePersonalInfo(BaseAccount):
    def execute(self, user_id, info_field, new_value):
        return self.repo.change_personal_info(user_id, info_field, new_value)

def change_personal_info(user_id, info_field, new_value):
    return ChangePersonalInfo().execute(user_id, info_field, new_value)

class CheckPassword(BaseAccount):
    def execute(self, user_id, password):
        return self.repo.check_password(user_id, password)

def check_smst_password(user_id, password):
    return CheckPassword().execute(user_id, password)
