"""Builds the PDF that goes with a stock receipt.

The cart hands over the figures before the line is deleted, so the receipt is
written from that snapshot and kept with the PDF. Nothing here reads the stock
ledger back.
"""

from __future__ import annotations

from decimal import Decimal

from core.reports.pdf import Document, as_count, fit_text

from .models import Receipt

GREEN = (18, 63, 39)
INK = (28, 23, 18)
MUTED = (120, 110, 100)
LINE = (223, 214, 205)
PAPER = (255, 255, 255)
BAND = (243, 249, 244)


def _money(value, currency: str) -> str:
    try:
        return f"{currency} {Decimal(str(value)):,.2f}"
    except (TypeError, ValueError, ArithmeticError):
        return f"{currency} 0.00"


def build_pdf(details: dict) -> bytes:
    """The receipt as a PDF."""
    document = Document(f"Receipt {details.get('reference', '')}")
    page = document.add_page()
    left = document.margin
    right = page.width - document.margin
    currency = details.get("currency", "")

    page.rect(0, 0, page.width, 12, GREEN)
    y = 48
    page.text(left, y, details.get("shop", "SmSt Africa"), size=18, bold=True, color=INK)
    y += 24
    for line in (
        details.get("shop_address", ""),
        details.get("shop_phone", ""),
        details.get("shop_email", ""),
    ):
        if line:
            page.text(left, y, line, size=9, color=MUTED)
            y += 13
    page.text(right, 48, "RECEIPT", size=10, bold=True, color=GREEN, align="right")
    page.text(
        right,
        64,
        details.get("reference", ""),
        size=9,
        color=INK,
        align="right",
    )
    page.text(
        right,
        77,
        details.get("created_at", ""),
        size=9,
        color=MUTED,
        align="right",
    )

    y = max(y + 10, 108)
    page.line(left, y, right, y, color=LINE, width=0.8)
    y += 20

    page.text(left, y, details.get("product", ""), size=12, bold=True, color=INK)
    if details.get("sku"):
        page.text(right, y, f"Code {details['sku']}", size=9, color=MUTED, align="right")
    y += 20
    page.text(
        left,
        y,
        f"{details.get('direction', 'Sale')} · {as_count(details.get('quantity'))} "
        f"{details.get('unit', '')}",
        size=10,
        color=MUTED,
    )
    y += 24

    page.rect(left, y, right - left, 22, BAND)
    page.text(left + 8, y + 6, "Unit price", size=9, color=MUTED)
    page.text(
        right - 8,
        y + 6,
        _money(details.get("unit_price"), currency),
        size=9,
        color=INK,
        align="right",
    )
    y += 38

    page.text(left, y, "Total", size=11, bold=True, color=INK)
    page.text(
        right,
        y,
        _money(details.get("total"), currency),
        size=14,
        bold=True,
        color=GREEN,
        align="right",
    )
    y += 34
    page.line(left, y, right, y, color=LINE, width=0.8)
    y += 18

    page.text(
        left,
        y,
        fit_text(
            f"Served by {details.get('served_by', '')}",
            size=9,
            max_width=right - left,
        ),
        size=9,
        color=MUTED,
    )
    y += 14
    page.text(left, y, details.get("kind", ""), size=9, color=MUTED)

    foot = "Thank you. This receipt was made with SmSt Africa."
    page.text(left, page.height - 58, foot, size=9, color=MUTED)
    return document.to_bytes()


def create_receipt(line, movement, user) -> Receipt:
    """Save the receipt for a cart line that has just been processed."""
    shop = movement.product.shop
    product = movement.product
    receipt = Receipt(
        shop=shop,
        movement=movement,
        created_by=user,
        details={
            "shop": shop.name,
            "shop_address": shop.address,
            "shop_phone": shop.phone,
            "shop_email": shop.email,
            "currency": shop.currency,
            "product": product.name,
            "sku": product.sku,
            "quantity": str(line.quantity),
            "unit": product.unit,
            "unit_price": str(line.unit_price),
            "total": str(line.total),
            "direction": line.get_direction_display(),
            "kind": movement.get_kind_display(),
            "served_by": user.get_full_name() or user.username,
            "created_at": movement.created_at.strftime("%d %b %Y, %H:%M"),
        },
    )
    receipt.details["reference"] = receipt.reference
    receipt.filename = f"receipt-{receipt.reference}.pdf"
    receipt.content = build_pdf(receipt.details)
    receipt.save()
    return receipt
