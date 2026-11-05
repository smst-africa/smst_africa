from django.http import HttpResponseRedirect
from core.utils import check_email
def smst_logged_in(func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return func(request, *args, **kwargs)
        return HttpResponseRedirect('https://user.smst.africa/')
    return wrapper

def check_email_wrapper(func):
    def wrapper(email, *args, **kwargs):
        if not check_email(email):
            return 
        return func(email, *args, **kwargs)
    return wrapper