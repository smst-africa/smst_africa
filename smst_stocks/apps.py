from django.apps import AppConfig


class SmstStocksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "smst_stocks"
    verbose_name = "SmSt Stocks"

    #: The path the app opens on, relative to the app host.
    start_url = "smst_stocks"
    #: The value the legacy app switcher uses to open this app.
    app_key = "smst_stocks"
    #: The display name used across the app.
    display_name = "SmSt Stocks"
    tagline = "Stocks, Shop, Analytics"
