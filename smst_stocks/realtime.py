"""Real time helpers for SmSt Stocks.

Every stock change is pushed to the shop owner's dashboard and to anyone
watching a shared product page. The channel layer is optional: if Redis is
down the update still succeeds, it just does not arrive instantly.
"""

import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger("smst")


def shop_group(username: str) -> str:
    return f"smst_stocks_{username}"


def product_group(product_id) -> str:
    return f"smst_stocks_product_{product_id}"


def group_send(group: str, payload: dict) -> bool:
    """Send a payload to a channel group. Never raises."""
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


def product_payload(product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "quantity": float(product.quantity),
        "reorder_level": float(product.reorder_level),
        "selling_price": float(product.selling_price),
        "buying_price": float(product.buying_price),
        "state": product.stock_state,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


def broadcast_product(product, event: str = "product.updated", extra: dict = None):
    """Tell the dashboard and the public page that a product changed."""
    data = product_payload(product)
    if extra:
        data.update(extra)

    group_send(
        shop_group(product.shop.owner.username),
        {"type": "stock_event", "event": event, "data": data},
    )
    group_send(
        product_group(product.id),
        {"type": "stock_event", "event": event, "data": data},
    )


def broadcast_shop(shop, event: str, data: dict):
    group_send(
        shop_group(shop.owner.username),
        {"type": "stock_event", "event": event, "data": data},
    )
