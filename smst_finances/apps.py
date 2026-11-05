from django.apps import AppConfig


class SmstFinancesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "smst_finances"
    verbose_name = "SmSt Finances"

    #: The path the app opens on, relative to the app host.
    start_url = "smst_finances"
    #: The value the legacy app switcher uses to open this app.
    app_key = "smst_finances"
    #: The display name used across the app.
    display_name = "SmSt Finances"
    tagline = "Money, Books, Insight"
