from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
import json

# Create your views here.
def frontend(request):
    view = request.GET.get('view')
    if view:
        return render(request, f'snippets/frontend/{view}.html')
    return render(request, 'frontend/smst.html')

def snippet_access(request, snippet):
    try:
        template = render(request, f'frontend/{snippet}.html')
    except:
        template = HttpResponseRedirect("https://smst.smst.africa")
    return template

from core.frontend.frontend import *
def user_access(request):
    
    action = request.GET.get('action')
    if action == "register-newsletter":
        data = json.loads(request.body)
        email = data.get('email')
        first_name = data.get('firstName')
        last_name = data.get('lastName')
        create_newsletter_user(email, first_name, last_name)
        return JsonResponse({
            "status":{
                email: email,
                first_name: first_name,
                last_name: last_name
            }
        })
    elif action == "unsubscribe_newsletter":
        email = request.GET.get('email')
        remove_news_letter_user(email)
        success_title = "Unsubscribed"
        success_content = "You have successfully unsubscribed from receiving SmSt Newsletter notifications."
        return render(request, 'snippets/notifications/success.html', {
            "success_title": success_title,
            "success_content": success_content
        })

import importlib

docs = {
    'privacy_policy':"core.docs.privacy_policy",
    'terms_of_use': 'core.docs.terms_of_use',
    'payment_policy': 'core.docs.payment_policy',
    'cookie_policy': 'core.docs.cookie_policy',
}

def documentation_access(request, doc):
    if doc:
        page = request.GET.get('page')
        if page:
            return render(request, f'docs/legals/extendors/{page}.html')
        sections = None
        sections = importlib.import_module(docs[doc]).sections
        if sections:
            return render(request, f'docs/legals/legal/{doc}.html', {'sections': sections})
        return HttpResponseRedirect('https://smst.smst.africa')