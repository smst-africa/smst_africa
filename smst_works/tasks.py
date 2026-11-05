"""Background work for SmSt Works.

A daily digest tells the owner how the team and the shop floor are doing. The
work is kept out of the request that saves a job.
"""

import logging

from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger("smst")

APP_URL = "https://app.smartstock.africa/smst_works/"


def _record_notification(user, title, content, instance):
    """Write a notification into the app notification centre."""
    from smst_app.models.notifications import AppNotifications

    return AppNotifications.objects.create(
        notificationTitle=title,
        notificationContent=content,
        notificationUser=user,
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
    )


@shared_task
def works_daily_digest():
    """A short workforce digest for every shop, once a day."""
    from smst_stocks.models import Shop

    from .services import dashboard_summary

    sent = 0
    for shop in Shop.objects.select_related("owner"):
        summary = dashboard_summary(shop)
        if not (
            summary["employees"]
            or summary["jobs"]
            or summary["customers"]
        ):
            continue

        content = (
            f"{summary['employees']} on the team, "
            f"{summary['running']} job"
            f"{'' if summary['running'] == 1 else 's'} running, "
            f"{summary['pending']} waiting, "
            f"{summary['customers']} loyalty customer"
            f"{'' if summary['customers'] == 1 else 's'} holding "
            f"{summary['points']} points."
        )

        try:
            _record_notification(
                shop.owner, "Daily workforce digest", content, shop
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not store the works digest", exc_info=True)

        sent += 1

    logger.info("Works digest sent for %s shops", sent)
    return {"shops": sent, "sent_at": timezone.now().isoformat()}
