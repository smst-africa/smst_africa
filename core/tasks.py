from celery import shared_task
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from .utils import *
from django.core.cache import cache
from django.contrib.auth import get_user_model
from .decorator import check_email_wrapper
import logging
logger = logging.getLogger('smst')
connection = get_connection()
from_email = "support@smartstock.africa"
UserModel = get_user_model()
def send_configured_email(subject, text_content, emails, html_content):
    email_msg = EmailMultiAlternatives(subject, text_content, from_email, emails)
    email_msg.attach_alternative(html_content, 'text/html')
    
    try:
        email_msg.send(fail_silently=False)
        print("Email Sent")
    except Exception as e:
        print(f"Error sending email: {e}")

@shared_task
def send_email(email):
    if not check_email(email):
        return
    emails = [email]
    unsubscribe_url = f"https://smst.africa/users/?action=unsubscribe_newsletter&email={email}"
    html_content = render_to_string('email/base_email.html', {'unsubscribe_newsletter_url': unsubscribe_url})
    text_content = "Welcome to Smartstock! (Use an HTML-compatible email viewer to see full content)"
    subject = "Welcome to SmSt"
    send_configured_email(subject, text_content, emails, html_content)


@shared_task
def send_otp_email(email):
    from backend.models import SmstUser
    if not check_email(email):
        return
    user_model = SmstUser.objects.filter(email=email).only('id')
    user = email.split("@")[0]

    if not user_model.exists():
        cache.set(f'new_user_{email}', True)

    cache_key = f'smst_otp_{user}'
    stored_otp = cache.get(cache_key)
    if stored_otp:
        return
    otp, hashed_otp = create_otp()
    cache.set(cache_key, hashed_otp, timeout=180)
    emails = [email]
    html_content = render_to_string('email/otp_email.html', {'otp': otp})
    text_content = "Verify your email! (Use an HTML-compatible email viewer to see full content)"
    subject = "Your verification OTP"
    send_configured_email(subject, text_content, emails, html_content)
        
# @check_email_wrapper
@shared_task
def send_link_email(email):
    
    emails = [email]
    logger.debug(emails)
    user_model = UserModel.objects.filter(email=email)
    if not user_model.exists():
        return  
    
    token, hashed_token = generate_link(email)
    html_content = render_to_string('email/link_email.html', {'token': token})
    
    text_content = "Reset your email! (Use an HTML-compatible email viewer to see full content)"
    subject = "Reset your password"
    send_configured_email(subject, text_content, emails, html_content)

# @check_email_wrapper
@shared_task
def send_receipt(email, receipt_id,purpose,amount, time):
    emails = [email]
    subject = "Payment Received"
    
    html_content = render_to_string('email/subscription_email.html', {'receipt_id': receipt_id, "purpose": purpose, "amount": amount, "time": time})
    text_content = "Payment Received (Use an HTML-compatible email viewer to see full content)"
    send_configured_email(subject, text_content, emails, html_content)
    

@shared_task
def send_notification(username, title, body, url="https://user.smst.africa", pro=False):
    from backend.models import SmstUserPushSubscription as PushModel
    from .utils import send_web_push
    subscription = PushModel.objects.filter(user__username=username)
    icon = 'https://res.cloudinary.com/di3bh4qsl/image/upload/v1780517418/latest_smst_logo_1_vrlvwa.png'
    if pro:
        icon = 'https://res.cloudinary.com/di3bh4qsl/image/upload/v1791388671/smst_pro_logo_fobkyu.png'
    for sub in subscription:
        
        send_web_push(sub, title, body, url, icon)
        
from django.apps import apps
@shared_task
def save_notification(title, content, username, model_name, field_id):
    from smst_app.models.notifications import AppNotifications
    model = apps.get_model('smst_app', model_name)
    user = UserModel.objects.filter(username=username).first()
    qs = model.objects.filter(id=field_id).first()
    AppNotifications.objects.create(
        notificationTitle=title,
        notificationContent=content,
        notificationUser=user,
        content_object = qs
    )
    send_notification.delay(username, title, content, pro=user.has_active_subscription)
    send_websocket_message.delay(username, title, content)
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()
@shared_task
def send_websocket_message(username, message_title, message_content, message_type=True):
    async_to_sync(channel_layer.group_send)(
        f'smst_app_{username}',
        {
            'type': 'send.event',
            'content': 'smst_notification',
            'data': {
                    'type': message_type,
                    'content_title': message_title,
                    'content_text': message_content
            }
        }
    )