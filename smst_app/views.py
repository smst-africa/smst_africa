"""Public landing pages for the three SmSt Apps.

The pages live outside the signed-in apps on purpose. They explain what each
app does before a shop owner creates an account, then hand over to the app.
"""

from django.shortcuts import render
from django.urls import reverse

ACCOUNT_URL = "https://user.smst.africa/"
APP_ROOT = "https://app.smst.africa"

APPS = {
    "works": {
        "name": "SmSt Works",
        "short": "Works",
        "kicker": "The shop floor",
        "initial": "W",
        "open_url": f"{APP_ROOT}/smst_works/",
        "page_title": "SmSt Works - the shop floor, in plain sight",
        "page_description": (
            "Run jobs, ranks, loyalty and suppliers from one live shop floor. "
            "Every person sees only the work their rank allows."
        ),
        "theme": "#1e4fa3",
    },
    "stocks": {
        "name": "SmSt Stocks",
        "short": "Stocks",
        "kicker": "The stock book",
        "initial": "S",
        "open_url": f"{APP_ROOT}/smst_stocks/",
        "page_title": "SmSt Stocks - the shelf, finally in one place",
        "page_description": (
            "Catalogue products, record every stock movement and see the value "
            "of the shelf without counting it by hand."
        ),
        "theme": "#a65a17",
    },
    "finances": {
        "name": "SmSt Finances",
        "short": "Finances",
        "kicker": "The money book",
        "initial": "F",
        "open_url": f"{APP_ROOT}/smst_finances/",
        "page_title": "SmSt Finances - every shilling on one page",
        "page_description": (
            "Record income, expenses, tax and drawings. Read statements, budgets "
            "and graphs from the same balanced book."
        ),
        "theme": "#1e5a36",
    },
}

ORDER = ("works", "stocks", "finances")


def _nav_apps(current):
    return [
        {
            "slug": slug,
            "name": APPS[slug]["name"],
            "short": APPS[slug]["short"],
            "kicker": APPS[slug]["kicker"],
            "url": reverse(f"{slug}"),
            "current": slug == current,
        }
        for slug in ORDER
    ]


def _landing(request, slug):
    app = {**APPS[slug], "slug": slug}
    return render(
        request,
        f"smst_app/{slug}.html",
        {
            "app": app,
            "apps": _nav_apps(slug),
            "account_url": ACCOUNT_URL,
            "icons_template": f"smst_{slug}/partials/icons.html",
            "theme_css": f"smst_app/css/{slug}.css",
        },
    )


def works(request):
    return _landing(request, "works")


def stocks(request):
    return _landing(request, "stocks")


def finances(request):
    return _landing(request, "finances")
