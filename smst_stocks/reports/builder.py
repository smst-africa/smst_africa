"""Builds the reports.

The same data feeds both writers, so the PDF and the spreadsheet always show
the same numbers.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from ..models import Order, Product, ReportRun, StockMovement
from ..services import low_stock_products, shop_buying_value, shop_stock_value
from core.reports.pdf import Document, as_count, as_text, fit_text, text_width
from core.reports.xlsx import STYLE_BOLD, STYLE_NUMBER, STYLE_TOTAL, STYLE_TOTAL_NUMBER, Workbook

logger = logging.getLogger("smst")

CARTON = (166, 90, 23)
CARTON_DARK = (122, 74, 22)
INK = (28, 23, 18)
MUTED = (120, 110, 100)
LINE = (223, 214, 205)
PAPER = (255, 255, 255)
BAND = (250, 246, 241)
LOW = (176, 106, 32)
OUT = (168, 50, 50)


# ------------------------------------------------------------------- data
def collect(run: ReportRun) -> dict:
    """Pull the rows the report needs out of the database."""
    shop = run.shop
    data = {
        "shop": shop,
        "kind": run.kind,
        "generated_at": timezone.now(),
        "title": run.get_kind_display(),
        "rows": [],
        "columns": [],
        "totals": [],
    }

    if run.kind == ReportRun.STOCK:
        products = Product.objects.filter(shop=shop).order_by("name")
        data["columns"] = [
            ("Item", "left", 150),
            ("SKU", "left", 70),
            ("In hand", "right", 60, "count"),
            ("Unit", "left", 50),
            ("Buying", "right", 70, "money"),
            ("Selling", "right", 70, "money"),
            ("Margin", "right", 60),
            ("Value", "right", 80, "money"),
        ]
        for product in products:
            data["rows"].append(
                [
                    product.name,
                    product.sku or "—",
                    product.quantity,
                    product.unit,
                    product.buying_price,
                    product.selling_price,
                    f"{product.margin:.1f}%",
                    product.stock_value,
                ]
            )
        data["totals"] = [
            "Total",
            "",
            "",
            "",
            shop_buying_value(shop),
            "",
            "",
            shop_stock_value(shop),
        ]
        data["note"] = f"{len(data['rows'])} items in {shop.name}."

    elif run.kind == ReportRun.MOVEMENTS:
        movements = StockMovement.objects.filter(product__shop=shop).select_related(
            "product", "created_by"
        )
        data["columns"] = [
            ("When", "left", 110),
            ("Item", "left", 150),
            ("Kind", "left", 80),
            ("Change", "right", 60, "count"),
            ("Note", "left", 170),
            ("By", "left", 90),
        ]
        for movement in movements:
            data["rows"].append(
                [
                    movement.created_at,
                    movement.product.name,
                    movement.get_kind_display(),
                    movement.quantity,
                    movement.note or "—",
                    (
                        movement.created_by.get_full_name()
                        or movement.created_by.username
                        if movement.created_by
                        else "—"
                    ),
                ]
            )
        data["note"] = f"{len(data['rows'])} movements recorded."

    elif run.kind == ReportRun.LOW_STOCK:
        data["columns"] = [
            ("Item", "left", 160),
            ("Category", "left", 80),
            ("In hand", "right", 60, "count"),
            ("Reorder at", "right", 70, "count"),
            ("Buying", "right", 70, "money"),
            ("Selling", "right", 70, "money"),
            ("Suggested order", "right", 90, "count"),
        ]
        for product in low_stock_products(shop):
            suggested = max(product.reorder_level * 2 - product.quantity, 0)
            data["rows"].append(
                [
                    product.name,
                    product.category or "—",
                    product.quantity,
                    product.reorder_level,
                    product.buying_price,
                    product.selling_price,
                    suggested,
                ]
            )
        data["note"] = f"{len(data['rows'])} items need ordering."

    else:  # orders
        orders = Order.objects.filter(shop=shop).select_related("product")
        data["columns"] = [
            ("Reference", "left", 90),
            ("When", "left", 110),
            ("Item", "left", 140),
            ("Quantity", "right", 60, "count"),
            ("Customer", "left", 120),
            ("Phone", "left", 100),
            ("Status", "left", 80),
            ("Total", "right", 80, "money"),
        ]
        total = 0
        for order in orders:
            total += float(order.total)
            data["rows"].append(
                [
                    order.reference,
                    order.created_at,
                    order.product.name,
                    order.quantity,
                    order.customer_name,
                    order.customer_phone,
                    order.get_status_display(),
                    order.total,
                ]
            )
        data["totals"] = ["Total", "", "", "", "", "", "", f"{total:,.2f}"]
        data["note"] = f"{len(data['rows'])} orders."

    return data


# -------------------------------------------------------------------- pdf
def build_pdf(run: ReportRun, data: dict) -> bytes:
    document = Document(title=f"{data['title']} — {data['shop'].name}")
    margin = 42
    width = document.page.width

    draw_header(document, data, margin, width)
    draw_table(document, data, margin, width)
    draw_footer(document, data, margin, width)

    return document.to_bytes()


def draw_header(document: Document, data: dict, margin: int, width: int):
    page = document.page
    page.rect(0, 0, width, 86, color=CARTON)
    page.text(margin, 30, "SmSt Stocks", 19, bold=True, color=PAPER)
    page.text(margin, 50, data["title"], 11, color=(245, 232, 218))
    page.text(margin, 66, data["shop"].name, 9, color=(245, 232, 218))

    generated = data["generated_at"].strftime("%d %b %Y, %H:%M")
    page.text(width - margin, 32, generated, 9, color=(245, 232, 218), align="right")
    page.text(
        width - margin,
        50,
        f"{data['shop'].currency}  ·  {data.get('note', '')}",
        9,
        color=(245, 232, 218),
        align="right",
    )


def draw_table(document: Document, data: dict, margin: int, width: int):
    columns = data["columns"]
    total_width = width - margin * 2
    scale = total_width / sum(column[2] for column in columns)
    positions = []
    left = margin
    for column in columns:
        column_width = column[2] * scale
        positions.append((left, column_width))
        left += column_width
    y = 110

    def header_row():
        nonlocal y
        page = document.page
        page.rect(margin, y - 6, total_width, 22, color=CARTON)
        for column, (x, column_width) in zip(columns, positions):
            label, align = column[0], column[1]
            page.text(
                x + (column_width - 6 if align == "right" else 6),
                y,
                label,
                8.5,
                bold=True,
                color=PAPER,
                align=align,
            )
        y += 26

    header_row()

    for index, row in enumerate(data["rows"]):
        if y > 760:
            document.add_page()
            y = 60
            header_row()

        page = document.page
        if index % 2 == 0:
            page.rect(margin, y - 6, total_width, 20, color=BAND)
        page.line(margin, y + 14, width - margin, y + 14, color=LINE)

        for value, column, (x, column_width) in zip(row, columns, positions):
            label, align = column[0], column[1]
            kind = column[3] if len(column) > 3 else "text"
            text = as_count(value) if kind == "count" else as_text(value)
            if align == "right":
                page.text(x + column_width - 6, y, text, 9, color=INK, align="right")
            else:
                page.text(
                    x + 6,
                    y,
                    fit_text(text, 9, column_width - 12),
                    9,
                    color=INK,
                )
        y += 20

    if data.get("totals"):
        page = document.page
        if y > 750:
            document.add_page()
            y = 60
        page.rect(margin, y - 6, total_width, 22, color=(247, 238, 228))
        page.line(margin, y - 6, width - margin, y - 6, color=CARTON, width=1)
        for value, column, (x, column_width) in zip(
            data["totals"], columns, positions
        ):
            label, align = column[0], column[1]
            kind = column[3] if len(column) > 3 else "text"
            text = as_count(value) if kind == "count" else as_text(value)
            if not text:
                continue
            if align == "right":
                page.text(
                    x + column_width - 6, y, text, 9.5, bold=True, color=CARTON_DARK, align="right"
                )
            else:
                page.text(x + 6, y, text, 9.5, bold=True, color=CARTON_DARK)


def draw_footer(document: Document, data: dict, margin: int, width: int):
    page = document.page
    page.line(margin, 790, width - margin, 790, color=LINE)
    page.text(
        margin,
        800,
        "SmSt Africa  ·  smst.africa",
        8,
        color=MUTED,
    )
    page.text(
        width - margin,
        800,
        f"Page {len(document.pages)}",
        8,
        color=MUTED,
        align="right",
    )


# ------------------------------------------------------------------ excel
def build_xlsx(run: ReportRun, data: dict) -> bytes:
    workbook = Workbook()
    sheet = workbook.add_sheet(data["title"][:31] or "Report")
    sheet.set_widths([column[2] / 6 for column in data["columns"]])

    sheet.append([f"{data['title']} — {data['shop'].name}"])
    sheet.append([f"Generated {data['generated_at'].strftime('%d %b %Y, %H:%M')}"])
    sheet.append([])
    sheet.header([column[0] for column in data["columns"]])
    sheet.freeze_rows = 5

    for row in data["rows"]:
        cells = []
        for index, value in enumerate(row):
            column = data["columns"][index] if index < len(data["columns"]) else ()
            kind = column[3] if len(column) > 3 else "text"
            if kind == "count" and isinstance(value, (int, float, Decimal)):
                cells.append((value, STYLE_NUMBER))
            elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                cells.append((value, STYLE_NUMBER))
            else:
                cells.append(value)
        sheet.append(cells)

    if data.get("totals"):
        sheet.append([])
        cells = []
        for index, value in enumerate(data["totals"]):
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                cells.append((value, STYLE_TOTAL_NUMBER))
            else:
                cells.append((value, STYLE_TOTAL))
        sheet.append(cells)

    return workbook.to_bytes()


# ----------------------------------------------------------------- build
def build_report(run: ReportRun) -> ReportRun:
    """Build the file for a report run and attach it to the record."""
    run.status = ReportRun.RUNNING
    run.save(update_fields=["status"])

    try:
        data = collect(run)
        if run.format == ReportRun.XLSX:
            content = build_xlsx(run, data)
            extension = "xlsx"
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            content = build_pdf(run, data)
            extension = "pdf"
            content_type = "application/pdf"

        slug = f"{run.shop.slug}-{run.kind}-{run.created_at:%Y%m%d-%H%M%S}.{extension}"
        run.filename = slug
        run.content = content
        run.status = ReportRun.READY
        run.error = ""
        run.save(update_fields=["status", "error", "filename", "content"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not build the report")
        run.status = ReportRun.FAILED
        run.error = str(exc)[:240]
        run.save(update_fields=["status", "error"])
        raise

    return run
