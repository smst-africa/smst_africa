"""Background work for SmSt Stocks.

Reports are built away from the request so that a big shop does not wait on a
file. Orders and low stock reach the shop owner by push notification, email
and the live dashboard.
"""

import logging

from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger("smst")

APP_URL = "https://app.smartstock.africa/smst_stocks/"


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


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_report(self, report_id):
    """Build a report and tell the shop it is ready."""
    from .models import ReportRun
    from .realtime import broadcast_shop
    from .reports.builder import build_report

    run = ReportRun.objects.filter(pk=report_id).first()
    if not run:
        return {"status": "missing"}

    try:
        build_report(run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Report %s could not be built", report_id)
        raise self.retry(exc=exc)

    run.refresh_from_db()
    broadcast_shop(
        run.shop,
        "report.ready",
        {
            "id": run.id,
            "kind": run.kind,
            "format": run.format,
            "status": run.status,
            "download_url": f"/smst_stocks/reports/{run.id}/download/",
        },
    )
    return {"status": run.status, "report": run.id}


@shared_task
def notify_new_order(order_id):
    """Tell the shop owner that a customer asked for stock."""
    from .models import Order

    order = (
        Order.objects.select_related("product", "shop", "shop__owner")
        .filter(pk=order_id)
        .first()
    )
    if not order:
        return {"status": "missing"}

    owner = order.shop.owner
    title = "New order"
    content = (
        f"{order.customer_name} asked for {order.quantity} {order.product.unit} "
        f"of {order.product.name}. Reference {order.reference}."
    )

    try:
        _record_notification(owner, title, content, order)
    except Exception:  # noqa: BLE001
        logger.warning("Could not store the order notification", exc_info=True)

    try:
        from core.tasks import send_notification

        send_notification.delay(
            owner.username, title, content, f"{APP_URL}orders/", owner.has_active_subscription
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not send the push notification", exc_info=True)

    try:
        from core.tasks import send_configured_email

        send_configured_email(
            subject=f"New order {order.reference}",
            text_content=content,
            emails=[owner.email] if owner.email else [],
            html_content=(
                f"<p>{content}</p>"
                f'<p><a href="{APP_URL}orders/">Open the order</a></p>'
            ),
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not send the order email", exc_info=True)

    return {"status": "sent", "order": order.reference}


@shared_task
def low_stock_digest():
    """A short list of the items that need ordering, sent once a day."""
    from .models import Shop
    from .services import low_stock_products

    sent = 0
    for shop in Shop.objects.select_related("owner"):
        items = low_stock_products(shop)
        if not items:
            continue

        lines = [f"{product.name} — {product.quantity} {product.unit} left" for product in items[:12]]
        content = "\n".join(lines)
        if len(items) > 12:
            content += f"\n...and {len(items) - 12} more."

        try:
            _record_notification(
                shop.owner, "Items to reorder", content, shop
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not store the low stock notification", exc_info=True)

        try:
            from core.tasks import send_notification

            send_notification.delay(
                shop.owner.username,
                "Items to reorder",
                f"{len(items)} items are running low.",
                f"{APP_URL}low-stock/",
                shop.owner.has_active_subscription,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not send the low stock push", exc_info=True)

        sent += 1

    logger.info("Low stock digest sent for %s shops", sent)
    return {"shops": sent, "sent_at": timezone.now().isoformat()}
