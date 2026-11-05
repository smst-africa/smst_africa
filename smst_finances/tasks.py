"""Background work for SmSt Finances.

Reports are built away from the request. A daily digest tells the owner what
came in, what went out and which budgets are close to their limit.
"""

import logging

from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger("smst")

APP_URL = "https://app.smartstock.africa/smst_finances/"


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
    """Build a finance report and tell the shop it is ready."""
    from .models import FinanceReport
    from .realtime import broadcast_shop
    from .reports.builder import build_report

    run = FinanceReport.objects.filter(pk=report_id).first()
    if not run:
        return {"status": "missing"}

    try:
        build_report(run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Finance report %s could not be built", report_id)
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
            "download_url": f"/smst_finances/reports/{run.id}/download/",
        },
    )
    return {"status": run.status, "report": run.id}


@shared_task
def finance_daily_digest():
    """A short money digest for every shop, once a day."""
    from smst_stocks.models import Shop

    from .services import dashboard_summary

    sent = 0
    for shop in Shop.objects.select_related("owner"):
        summary = dashboard_summary(shop)
        if not summary["count"] and not summary["budget_count"]:
            continue

        content = (
            f"In {shop.currency} {summary['income']:,.2f}, "
            f"out {shop.currency} {summary['expense']:,.2f}, "
            f"net {shop.currency} {summary['net']:,.2f}. "
            f"Cash at hand {shop.currency} {summary['cash']:,.2f}, "
            f"tax due {shop.currency} {summary['tax_due']:,.2f}."
        )

        try:
            _record_notification(shop.owner, "Daily money digest", content, shop)
        except Exception:  # noqa: BLE001
            logger.warning("Could not store the finance digest", exc_info=True)

        try:
            from core.tasks import send_notification

            send_notification.delay(
                shop.owner.username,
                "Daily money digest",
                content,
                f"{APP_URL}",
                shop.owner.has_active_subscription,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not send the finance push", exc_info=True)

        try:
            from core.tasks import send_configured_email

            send_configured_email(
                subject="Your daily money digest",
                text_content=content,
                emails=[shop.owner.email] if shop.owner.email else [],
                html_content=(
                    f"<p>{content}</p>"
                    f'<p><a href="{APP_URL}">Open SmSt Finances</a></p>'
                ),
            )
        except Exception:  # noqa: BLE001
            logger.warning("Could not send the finance email", exc_info=True)

        sent += 1

    logger.info("Finance digest sent for %s shops", sent)
    return {"shops": sent, "sent_at": timezone.now().isoformat()}


@shared_task
def budget_alerts():
    """Tell the owner when a budget is 80% used or over its limit."""
    from .models import FinanceBudget
    from .services import budget_status

    alerts = 0
    for budget in FinanceBudget.objects.select_related("shop", "shop__owner"):
        status = budget_status(budget)
        if status["percent"] < 80:
            continue

        state = "over its limit" if status["percent"] >= 100 else "80% used"
        content = (
            f"{budget.name} is {state}: {budget.shop.currency} "
            f"{status['spent']:,.2f} of {budget.amount:,.2f}."
        )
        try:
            _record_notification(budget.shop.owner, "Budget alert", content, budget)
            alerts += 1
        except Exception:  # noqa: BLE001
            logger.warning("Could not store the budget alert", exc_info=True)

    return {"alerts": alerts}
