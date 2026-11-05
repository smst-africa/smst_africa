from django.shortcuts import render
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse, HttpResponseRedirect
def app(request):
    user = request.user
    refresh = RefreshToken.for_user(user)
    action = request.GET.get('action')
    if action == "any_unread_notifications":
        from core.app.notification import any_unread_notifications
        return JsonResponse({
            'status': any_unread_notifications(user.id)
        })
    return render(request, 'app/homepage.html',{
        'refresh': str(refresh),
        'access': str(refresh.access_token)
    })
    
def login(request):
    return HttpResponseRedirect('https://user.smst.africa/')


def smst_app(request):
    app = request.GET.get('smst_app')
    if app:
        # SmSt Stocks has a home of its own. The old switcher link lands there.
        if app == "smst_stocks":
            return HttpResponseRedirect(reverse("smst_stocks:dashboard"))
        # SmSt Finances opens on its own money book.
        if app == "smst_finances":
            return HttpResponseRedirect(reverse("smst_finances:dashboard"))
        # SmSt Works opens on the live shop-floor timeline.
        if app == "smst_works":
            return HttpResponseRedirect(reverse("smst_works:dashboard"))
        trigger = False
        if app == "smst_stocks":
            if request.user.is_authenticated:
                trigger = request.user.has_stock
        return render(request, f'app/apps/{app}.html', {'trigger': trigger })

    action = request.GET.get('action')
    if action == "create_smst_stock":
        return render(request, 'app/apps/smst_stocks/forms/create_product.html')
    
    forms = request.GET.get('forms')
    if forms:
        return render(request, f'app/apps/smst_stocks/forms/{forms}.html')