from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import uuid
import logging
logger = logging.getLogger('smst')
def check_email(email):
    try:
        validate_email(email)
        return True
    except:
        return False

import secrets, hashlib

def create_otp():
    otp =  str(secrets.randbelow(1_000_000)).zfill(6)
    hashed_otp = hashlib.sha256(otp.encode()).hexdigest()
    return ( otp, hashed_otp)

def generate_link(email):
    token = secrets.token_urlsafe(32)
    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    cache_key = f'smst_reset_{hashed_token}'
    cache.set(cache_key, email, timeout=30*60)
    return (token, hashed_token)    

def confirm_link(token):
    clean_token = hashlib.sha256(token.encode()).hexdigest()
    email = cache.get(f'smst_reset_{clean_token}')
    if email:
        return email
    return False


def delete_stored_link(token):
    clean_token = hashlib.sha256(token.encode()).hexdigest()
    email = cache.delete(f'smst_reset_{clean_token}')

from django.core.cache import cache
def confirm_otp(otp, id):
    encoded_otp = cache.get(f'smst_otp_{id}')
    otp_clean = hashlib.sha256(otp.encode()).hexdigest()
    if secrets.compare_digest(otp_clean, encoded_otp):
        return True
    return False

def confirm_user(email):
    from backend.models import SmstUser
    return SmstUser.objects.filter(email=email).exists()

def confirm_social(email):
    from backend.models import SmstUser
    return SmstUser.objects.filter(email=email, social_acc=True).exists()

import json
from django.conf import settings
from pywebpush import webpush, WebPushException

def send_web_push(subscription, title, body, url, icon):
    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {
            'p256dh': subscription.p256dh,
            'auth': subscription.auth,
        }
    }
    
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon,
        "badge": 'https://res.cloudinary.com/di3bh4qsl/image/upload/v1790847358/smst_logo_badge_ix7iyn.png',
        "url": url
    })
    
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key = settings.VAPID_PRIVATE_KEY,
            vapid_claims={
                'sub': settings.VAPID_EMAIL
            }
        )
    except WebPushException as e:
        logger.critical(f'Web Push Sub Sending Error {e}')

def generate_pro_code():
    from backend.models import SmstSubscription
    while True:
        code = f'PRO_{uuid.uuid4().hex[:10]}'
        if not SmstSubscription.objects.filter(subscription_code=code).exists():
            return code

def generate_notification_id():
    from smst_app.models import AppNotifications
    while True:
        notifId = str(uuid.uuid4())
        if not AppNotifications.objects.filter(notificationId=notifId).exists():
            return notifId

from decouple import config
import requests
def initialize_paystack_transacton(email, amount):
    url = 'https://api.paystack.co/transaction/initialize'
    secret_key = settings.PAYSTACK_SECRET_KEY
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        'email': email,
        "amount": amount,
        "callback_url": "https://user.smst.africa/accounts/profile/?view_page=smst_pro_verification"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def verify_paystack_transaction(reference):
    url = "https://api.paystack.co/transaction/verify"
    secret_key = settings.PAYSTACK_SECRET_KEY
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        'reference':reference
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    logger.debug(response)
    return response.json()

import hmac
from django.conf import settings
def get_signature(header_signature, payload):
    return header_signature == hmac.new(
        key = settings.PAYSTACK_SECRET_KEY.encode(),
        msg=payload,
        digestmod=hashlib.sha512
    ).hexdigest()


