from dataclasses import dataclass
from backend.models import SmstUser, SmstSubscription, ProPlan, SubscriptionPayment
from django.db import transaction
from decimal import Decimal
from core.tasks import send_receipt, send_notification
from django.utils.translation import gettext as _

@dataclass
class SmstPro:
    pro_user_email: str
    pro_ref_no: str
    pro_sub_amount: str
    
class ProEntity:
    @transaction.atomic
    def make_smst_user_pro(self, smst_pro:SmstPro)->bool:
        user = SmstUser.objects.filter(email=smst_pro.pro_user_email).first()
        proplan = ProPlan.objects.filter(name="SmstPro").first()
        subscription, created= SmstSubscription.objects.get_or_create(
            user=user,
            plan=proplan
        )
        
        instance, created = SubscriptionPayment.objects.get_or_create(
            subscription = subscription,
            transaction_id=smst_pro.pro_ref_no,
            defaults={
            'amount':Decimal(f'{smst_pro.pro_sub_amount}')/Decimal('100'),
            }
        )
        
        send_receipt.delay(
                instance.subscription.user.email,
                instance.transaction_id,
                f"{instance.subscription.plan.name} Subscription",
                Decimal(f'{instance.amount}')/Decimal('100'),
                instance.subscription.start_date,
            )

        send_notification.delay(user.username, _('Upgraded to Smst Pro'), _('Enjoy Premium Experience'), 'https://user.smst.africa/accounts/profile/?view_page=smstpro', user.has_active_subscription)
        
        
        
class BasePro:
    def __init__(self):
        self.repo = ProEntity()

class MakeUserPro(BasePro):
    def execute(self, ref_no, email, amount):
        smst_pro = SmstPro(
            pro_user_email=email,
            pro_ref_no=ref_no,
            pro_sub_amount=amount
        )
        return self.repo.make_smst_user_pro(smst_pro)

def make_user_pro(ref_no, email, amount):
    return MakeUserPro().execute(ref_no, email, amount)
    