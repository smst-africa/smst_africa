from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import HttpRequest
from allauth.socialaccount.models import SocialLogin
from backend.models import SmstUser
from django.contrib.auth import authenticate, login

class SmstAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request:HttpRequest, sociallogin:SocialLogin) -> None:
        if sociallogin.is_existing:
            return
        if not sociallogin.account.extra_data.get("email_verified", False):
            return
        
        email = sociallogin.user.email
        
        try:
            user = SmstUser.objects.get(email__iexact=email)
        except SmstUser.DoesNotExist:
            return

        sociallogin.connect(request, user)