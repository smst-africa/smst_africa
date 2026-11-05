"""Real time helpers for SmSt Finances.

Every finance change is pushed to the shop owner's dashboard. The channel layer
is optional: if Redis is down the write still succeeds, it just does not arrive
instantly.
"""

import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger("smst")


def shop_group(username: str) -> str:
    return f"smst_finances_{username}"


def group_send(group: str, payload: dict) -> bool:
    try:
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return False
        async_to_sync(layer.group_send)(group, payload)
        return True
    except Exception:  # noqa: BLE001 - realtime must never break a write
        logger.warning("Could not reach the channel layer for %s", group, exc_info=True)
        return False


def broadcast_shop(shop, event: str, data: dict) -> bool:
    return group_send(
        shop_group(shop.owner.username),
        {"type": "finance_event", "event": event, "data": data},
    )


def broadcast_entry(entry, event: str = "finance.entry.created") -> bool:
    from .services import dashboard_summary

    summary = dashboard_summary(entry.shop)
    return broadcast_shop(
        entry.shop,
        event,
        {
            "id": entry.id,
            "reference": entry.reference,
            "kind": entry.kind,
            "amount": float(entry.amount),
            "description": entry.description,
            "summary": {
                "income": float(summary["income"]),
                "expense": float(summary["expense"]),
                "net": float(summary["net"]),
                "cash": float(summary["cash"]),
                "tax_due": float(summary["tax_due"]),
                "count": summary["count"],
            },
        },
    )


def broadcast_option(option, event: str = "finance.option.updated") -> bool:
    return broadcast_shop(
        option.shop,
        event,
        {"id": option.id, "name": option.name, "kind": option.kind},
    )


def broadcast_chart(chart, event: str = "finance.chart.updated") -> bool:
    return broadcast_shop(
        chart.shop,
        event,
        {"id": chart.id, "title": chart.title, "chart_type": chart.chart_type},
    )
