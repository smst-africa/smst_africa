from django.shortcuts import render
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from core.account.account import *
from django.template.loader import render_to_string
from django.shortcuts import redirect
import json
from django.contrib.auth import authenticate, login
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import logout
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
import logging
logger = logging.getLogger('smst')

def logout_session(request):
    from core.account.account import remove_notifications
    user = request.user
    remove_notifications(user.username)
    logout(request)
@csrf_exempt
def webhook(request):
    from core.utils import get_signature
    if request.method != "POST":
        return HttpResponse(status=405)
    
    provider = request.GET.get('provider')
    if provider == "paystack":
        action = request.GET.get('action')
        if action == "successPayment":
            payload = request.body
            logger.debug(type(payload))
            valid_sign = get_signature(request.headers.get('x-paystack-signature'), payload)
            if not valid_sign:
                return HttpResponse(status=401)
            
            data = json.loads(payload)
            if data.get('event') == "charge.success":
                from core.account.pro import make_user_pro
                data = data['data']
                reference = data['reference']
                email = data['customer']['email']
                amount = data['amount']
                make_user_pro(reference, email, amount)
                return HttpResponse(status=200)
            
            computed_signature

@ratelimit(key="post:email", rate="50/m")
def user(request):
    action = request.GET.get('action')
    user = request.user
    if action == "check_username":
        username = request.GET.get('username').lower()
        if user.is_authenticated:
            if username == user.username:
                return JsonResponse({"status": 'valid'})
            
        exist = check_username(username)
        return JsonResponse({"status": exist})
    if action == "update_username":
        data = json.loads(request.body)
        username = data.get('username')
        changed = change_username(username, user.id)
        return JsonResponse({"status": changed})
    if action == "verify_email":
        from core.tasks import send_otp_email
        from core.utils import confirm_user
        data = json.loads(request.body)
        
        email = data.get('email')
        user = confirm_user(email)
        if not user:
            request.session['new_user'] = email.split("@")[0]
        send_otp_email.delay(email)
        request.session['email'] = email
        return render(request, 'user/page/otp.html', {"otpType": action.split("_")[0]})
    if action == "validate_email":
        from core.tasks import confirm_otp
        from django.core.cache import cache
        data = json.loads(request.body)
        otp = data.get('otp')
        email = request.session.get('email')
        code = cache.get(f'new_user_{email}')
        try:
            valid = confirm_otp(otp, email.split("@")[0])
        
            if code:
                return JsonResponse({
                    'status': valid,
                    'html': render_to_string('user/page/password.html')
                })

            if valid: 
                from core.utils import confirm_user, confirm_social
                user = confirm_user(email)
                if user:
                    social = confirm_social(email)
                    if social:
                        return JsonResponse({
                            'status': 'social_auth',
                            'url': '/accounts/google/login/?process=login'
                        })
                return JsonResponse({
                    'status': valid,
                    'html': render_to_string('user/page/login.html', {'email': email})
                })
            
        except Exception:
            return JsonResponse({
                'status': False
            })
    if action == "create_account":
        data = json.loads(request.body)
        password = data.get('password')
        account = create_account(request.session.get('email'), password)
        if account:
            request.session.delete('email')
        return JsonResponse({
            'status': account
        })
    if action == "login_user":
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        user = authenticate(request=request,email=email, password=password) 
        status = False
        if user:
            status = True
            login(request, user)
        return JsonResponse({
            'status': status
        })
    if action == "reset_email":
        from core.tasks import send_link_email
        data = json.loads(request.body)
        email = request.session.get('email')
        send_link_email.delay(email or data.get('email'))
        return render(request, 'user/page/reset_link.html')
    if action == "reset_password":
        from core.tasks import confirm_link
        token = request.GET.get('token')
        email = confirm_link(token)
        if email:
            return render(request, 'user/page/password_reset.html')
        return HttpResponseRedirect('https://user.smst.africa')
    if action == "change_password":
        from core.tasks import confirm_link
        data = json.loads(request.body)
        password1 = data.get('password1')
        password2 = data.get('password2')
        token = data.get('token')
        email = confirm_link(token)
        if password1 == password2 and email:
            from core.account.account import change_password
            from core.utils import delete_stored_link
            changed = change_password(email, password1)
            if changed:
                delete_stored_link(token)
            return JsonResponse({
                'status': changed,
                'html': render_to_string('user/page/login.html', {'email': email})
            })
        return JsonResponse({
            'status': False
        })
            
    page = request.GET.get('page')
    if page == "login_user":
        return render(request, 'user/page/login.html')
    if page == 'reset_password':
        return render(request, 'user/page/reset_email.html')
    if user.is_authenticated:
        return HttpResponseRedirect('https://user.smst.africa/accounts/profile')
    
    return render(request, 'user/page/signup.html')
from core.decorator import smst_logged_in
import logging
logger = logging.getLogger('smst')
@smst_logged_in
def profile(request):
    user = request.user
    if not user.username:
        return render(request, 'user/profile/username.html')
    page = request.GET.get('page')
    if page:
        data = None
        if page == "notifications":
            endpoint = request.session.get('endpoint')
            data = {'pager': endpoint}
        if page == "smstpro" and user.has_active_subscription:
            return render(request, f'user/profile/pages/minipages/smst_pro_verification.html')
        return render(request, f'user/profile/pages/minipages/{page}.html', data)
    
    action = request.GET.get('action')
    if action == "check_notifications":
        from core.account.account import check_notification
        return JsonResponse({
            'status': check_notification(user, request.GET.get('endpoint'))
        })
    if action == "activate_notifications":
        from core.account.account import enable_notifications
        data = json.loads(request.body)
        endpoint = data.get('endpoint')
        keys = data.get('keys')
        notifications = enable_notifications(endpoint, keys['p256dh'], keys['auth'],user.id)
        if notifications:
            request.session['endpoint']=endpoint
        return JsonResponse({
            'status': notifications
        })
    if action == "silence_notifications":
        from core.account import silence_notifications
        data = json.loads(request.body)
        endpoint = data.get('endpoint')
        silenced = silence_notifications(endpoint, user.id)
        return JsonResponse({
            'status': silenced
        })
    if action == "edit":
        value = request.GET.get('value')
        input_value = request.GET.get('input')
        clean_name = value.split("_")
        edit_name = " ".join(clean_name)
        return render(request, 'user/profile/pages/editingpages/edit.html', {'edit_name':edit_name, 'input_id':value, "input_value":input_value})    
    if action == "edit_personal_info":
        from core.account.account import change_personal_info
        data = json.loads(request.body)
        edit_name = data.get('editName')
        edit_value = data.get('editValue')
        change = change_personal_info(user.id, edit_name, edit_value)
        return JsonResponse({
            'status': change
        })
    if action == "change_password":
        verification = request.GET.get('verification')
        if verification:
            from core.account.account import change_password
            data = json.loads(request.body)
            password = data.get('password')
            changed = change_password(user.email, password)
            if changed:
                logout_session(request)
            return JsonResponse({'status': changed})
        return render(request, 'user/profile/pages/verification/password.html')
    if action == "confirm_password":
        from core.account.account import check_smst_password
        data = json.loads(request.body)
        password = data.get('password')
        cache_key = f'incorrect_login_attempts_{user.id}'
        confirmation = check_smst_password(user.id, password)
        if confirmation:
            cache.delete(cache_key)
            return JsonResponse({
                'status': confirmation,
                'html': render_to_string('user/profile/pages/verification/password_change.html')
            })
        else:
            attempts = cache.get(cache_key) or 0
            if attempts >=3:
                logout_session(request)
                return JsonResponse({'status': confirmation, 'logout': True})
            attempts += 1
            cache.set(cache_key, attempts, timeout=3600)
        return JsonResponse({'status': confirmation})
    if action == "logout":
        logout_session(request)
        return JsonResponse({'status': True})
    if action == "init_paystack":
        from core.utils import initialize_paystack_transacton
        response = initialize_paystack_transacton(user.email, '49900')
        return JsonResponse({'response': response})
    if action == "check_newsletter_subscription":
        from core.frontend.frontend import check_newsletter_subscription
        subscription = check_newsletter_subscription(user.email)
        return JsonResponse({
            'status': subscription
        })
    if action == "subscribe_newsletter":
        from core.frontend.frontend import create_newsletter_user
        subscribed = create_newsletter_user(user.email, user.first_name, user.last_name)
        return JsonResponse({
            'status': subscribed
        })
    return render(request, 'user/profile/page.html' ,{'vapid_public_key': settings.PROCESSED_VAPID_PUBLIC_KEY})

@smst_logged_in
def cake(request):
    return render(request, 'cake/cake.html')