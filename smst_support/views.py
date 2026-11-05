"""Views for the SmSt support centre.

The pages are public and read their copy from :mod:`smst_support.content`.
No model and no migration is involved.
"""

from django.shortcuts import render

from . import content


def _context(app, support, icons_template, theme_css):
    return {
        "app": app,
        "support": support,
        "apps": content.nav_apps(),
        "support_apps": content.support_apps(),
        "account_url": content.ACCOUNT_URL,
        "contact_email": content.CONTACT_EMAIL,
        "icons_template": icons_template,
        "theme_css": theme_css,
        "support_active": True,
    }


def hub(request):
    support = content.hub()
    return render(
        request,
        "smst_support/hub.html",
        _context(
            content.HUB_APP,
            support,
            "smst_works/partials/icons.html",
            "smst_support/css/support.css",
        ),
    )


def app(request, slug):
    support = content.support_app(slug)
    return render(
        request,
        "smst_support/app.html",
        _context(
            support,
            support,
            f"smst_{slug}/partials/icons.html",
            f"smst_app/css/{slug}.css",
        ),
    )
