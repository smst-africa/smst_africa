"""Real time helpers for SmSt Works.

A change on the shop floor is pushed to everyone in the shop's group. The
channel layer is optional: if Redis is down the write still succeeds, it just
does not arrive instantly.
"""

import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger("smst")


def shop_group(shop_id) -> str:
    return f"smst_works_shop_{shop_id}"


def group_send(group: str, payload: dict) -> bool:
    try:
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return False
        async_to_sync(layer.group_send)(group, payload)
        return True
    except Exception:  # noqa: BLE001 - realtime must never break a write
        logger.warning(
            "Could not reach the channel layer for %s", group, exc_info=True
        )
        return False


def broadcast_shop(shop, event: str, data: dict) -> bool:
    shop_id = getattr(shop, "pk", shop)
    return group_send(
        shop_group(shop_id),
        {"type": "works_event", "event": event, "data": data},
    )


def broadcast_job(job, event: str = "works.job.updated") -> bool:
    from .services import dashboard_summary

    return broadcast_shop(
        job.shop,
        event,
        {
            "id": job.id,
            "title": job.title,
            "status": job.status,
            "summary": dashboard_summary(job.shop),
        },
    )
