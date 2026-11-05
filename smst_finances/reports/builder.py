"""Builds the finance reports.

The same data feeds both writers, so the PDF and the spreadsheet always show
the same figures.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from smst_finances.models import FinanceBudget, FinanceEntry, FinanceReport
from smst_finances.services import (
    balance_sheet,
    budget_status,
    cash_flow,
    general_ledger,
    profit_and_loss,
    trial_balance,
)

from core.reports.pdf import Document, as_count, as_text, fit_text, text_width
from core.reports.xlsx import STYLE_BOLD, STYLE_NUMBER, STYLE_TOTAL, STYLE_TOTAL_NUMBER, Workbook

logger = logging.getLogger("smst")

GREEN = (18, 63, 39)
GREEN_DARK = (12, 47, 28)
INK = (28, 23, 18)
MUTED = (120, 110, 100)
LINE = (223, 214, 205)
PAPER = (255, 255, 255)
BAND = (243, 249, 244)


def _entry_rows(entries, include_kind=False):
    rows = []
    for entry in entries.select_related("option", "product", "movement"):
        row = [
            timezone.localtime(entry.occurred_at),
            entry.reference,
            entry.description,
            entry.option.name if entry.option else "—",
            entry.product.name if entry.product else "—",
        ]
        if include_kind:
            row.append(entry.get_kind_display())
        row.append(entry.amount)
        rows.append(row)
    return rows


def collect(run: FinanceReport) -> dict:
    """Pull the rows the report needs out of the database."""
    shop = run.shop
    start = run.date_from
    end = run.date_to
    data = {
        "shop": shop,
        "kind": run.kind,
        "generated_at": timezone.now(),
        "title": run.get_kind_display(),
        "rows": [],
        "columns": [],
        "totals": [],
    }

    entries = FinanceEntry.objects.filter(
        shop=shop, status=FinanceEntry.POSTED
    )
    if start:
        entries = entries.filter(occurred_at__date__gte=start)
    if end:
        entries = entries.filter(occurred_at__date__lte=end)

    if run.kind == FinanceReport.INCOME:
        rows = _entry_rows(entries.filter(kind__in=(FinanceEntry.INCOME, FinanceEntry.PROFIT)))
        data["columns"] = [
            ("When", "left", 112),
            ("Reference", "left", 82),
            ("What it was for", "left", 170),
            ("Option", "left", 100),
            ("Product", "left", 100),
            ("Amount", "right", 80, "money"),
        ]
        data["rows"] = rows
        total = sum((row[-1] for row in rows), Decimal("0"))
        data["totals"] = ["Total", "", "", "", "", total]
        data["note"] = f"{len(rows)} income entries."

    elif run.kind == FinanceReport.EXPENSES:
        kinds = (
            FinanceEntry.EXPENSE,
            FinanceEntry.LOSS,
            FinanceEntry.DISCOUNT,
            FinanceEntry.REFUND,
            FinanceEntry.TAX,
        )
        rows = _entry_rows(entries.filter(kind__in=kinds), include_kind=True)
        data["columns"] = [
            ("When", "left", 112),
            ("Reference", "left", 82),
            ("What it was for", "left", 160),
            ("Option", "left", 95),
            ("Product", "left", 95),
            ("Kind", "left", 70),
            ("Amount", "right", 76, "money"),
        ]
        data["rows"] = rows
        total = sum((row[-1] for row in rows), Decimal("0"))
        data["totals"] = ["Total", "", "", "", "", "", total]
        data["note"] = f"{len(rows)} expense entries."

    elif run.kind == FinanceReport.PROFIT_LOSS:
        pnl = profit_and_loss(shop, start, end)
        data["columns"] = [
            ("Code", "left", 60),
            ("Account", "left", 220),
            ("Type", "left", 80),
            ("Amount", "right", 100, "money"),
        ]
        for row in pnl["income"]:
            data["rows"].append([row["code"], row["name"], "Income", row["amount"]])
        for row in pnl["expense"]:
            data["rows"].append([row["code"], row["name"], "Expense", row["amount"]])
        data["totals"] = ["", "Net profit", "", pnl["net"]]
        data["note"] = (
            f"Income {shop.currency} {pnl['income_total']:,.2f} · "
            f"Expenses {shop.currency} {pnl['expense_total']:,.2f}."
        )

    elif run.kind == FinanceReport.TAX:
        tax_entries = entries.filter(kind=FinanceEntry.TAX).select_related(
            "option", "account"
        )
        data["columns"] = [
            ("When", "left", 112),
            ("Reference", "left", 82),
            ("Tax", "left", 140),
            ("Account", "left", 120),
            ("Amount", "right", 90, "money"),
        ]
        total = Decimal("0")
        for entry in tax_entries:
            total += entry.amount
            data["rows"].append(
                [
                    timezone.localtime(entry.occurred_at),
                    entry.reference,
                    entry.option.name if entry.option else entry.description,
                    entry.account.name if entry.account else "—",
                    entry.amount,
                ]
            )
        data["totals"] = ["Total", "", "", "", total]
        data["note"] = f"{len(data['rows'])} tax entries."

    elif run.kind == FinanceReport.CASH_FLOW:
        flow = cash_flow(shop, start, end)
        data["columns"] = [
            ("When", "left", 112),
            ("Reference", "left", 82),
            ("What it was for", "left", 170),
            ("Account", "left", 90),
            ("In", "right", 70, "money"),
            ("Out", "right", 70, "money"),
            ("Net", "right", 70, "money"),
        ]
        for row in flow["rows"]:
            data["rows"].append(
                [
                    timezone.localtime(row["date"]),
                    row["reference"],
                    row["description"],
                    row["account"],
                    row["inflow"],
                    row["outflow"],
                    row["net"],
                ]
            )
        data["totals"] = [
            "Total",
            "",
            "",
            "",
            flow["inflow_total"],
            flow["outflow_total"],
            flow["net"],
        ]
        data["note"] = f"Cash movement from {flow['start']} to {flow['end']}."

    elif run.kind == FinanceReport.TRIAL_BALANCE:
        trial = trial_balance(shop, start, end)
        data["columns"] = [
            ("Code", "left", 60),
            ("Account", "left", 220),
            ("Type", "left", 80),
            ("Debit", "right", 90, "money"),
            ("Credit", "right", 90, "money"),
        ]
        for row in trial["rows"]:
            data["rows"].append(
                [row["code"], row["name"], row["type"], row["debit"], row["credit"]]
            )
        data["totals"] = [
            "",
            "Total",
            "",
            trial["total_debit"],
            trial["total_credit"],
        ]
        data["note"] = "Debits and credits must agree."

    elif run.kind == FinanceReport.BALANCE_SHEET:
        sheet = balance_sheet(shop, start, end)
        data["columns"] = [
            ("Code", "left", 60),
            ("Account", "left", 220),
            ("Type", "left", 90),
            ("Amount", "right", 100, "money"),
        ]
        for row in sheet["assets"]:
            data["rows"].append([row["code"], row["name"], "Asset", row["amount"]])
        for row in sheet["liabilities"]:
            data["rows"].append(
                [row["code"], row["name"], "Liability", row["amount"]]
            )
        for row in sheet["equity"]:
            data["rows"].append([row["code"], row["name"], "Equity", row["amount"]])
        data["totals"] = ["", "Assets", "", sheet["assets_total"]]
        data["note"] = (
            f"Liabilities {shop.currency} {sheet['liabilities_total']:,.2f} · "
            f"Equity {shop.currency} {sheet['equity_total']:,.2f}."
        )

    elif run.kind == FinanceReport.GENERAL_LEDGER:
        ledger = general_ledger(shop, start, end)
        data["columns"] = [
            ("When", "left", 100),
            ("Reference", "left", 70),
            ("Account", "left", 130),
            ("Description", "left", 150),
            ("Debit", "right", 75, "money"),
            ("Credit", "right", 75, "money"),
        ]
        for entry in ledger["rows"]:
            for line in entry.lines.all():
                data["rows"].append(
                    [
                        timezone.localtime(entry.occurred_at),
                        entry.reference,
                        f"{line.account.code} {line.account.name}",
                        line.description or entry.description,
                        line.debit,
                        line.credit,
                    ]
                )
        data["note"] = f"{len(data['rows'])} ledger lines."

    else:  # budgets
        data["columns"] = [
            ("Budget", "left", 160),
            ("Period", "left", 70),
            ("Starts", "left", 80),
            ("Amount", "right", 80, "money"),
            ("Spent", "right", 80, "money"),
            ("Left", "right", 80, "money"),
            ("Used", "right", 50),
        ]
        for budget in FinanceBudget.objects.filter(shop=shop):
            status = budget_status(budget)
            data["rows"].append(
                [
                    budget.name,
                    budget.get_period_display(),
                    status["start"],
                    budget.amount,
                    status["spent"],
                    status["remaining"],
                    f"{status['percent']:.1f}%",
                ]
            )
        data["note"] = f"{len(data['rows'])} budgets."

    return data


# -------------------------------------------------------------------- pdf
def build_pdf(run: FinanceReport, data: dict) -> bytes:
    document = Document(title=f"{data['title']} — {data['shop'].name}")
    margin = 42
    width = document.page.width

    draw_header(document, data, margin, width)
    draw_table(document, data, margin, width)
    draw_footer(document, data, margin, width)

    return document.to_bytes()


def draw_header(document: Document, data: dict, margin: int, width: int):
    page = document.page
    page.rect(0, 0, width, 86, color=GREEN)
    page.text(margin, 30, "SmSt Finances", 19, bold=True, color=PAPER)
    page.text(margin, 50, data["title"], 11, color=(224, 241, 229))
    page.text(margin, 66, data["shop"].name, 9, color=(224, 241, 229))

    generated = data["generated_at"].strftime("%d %b %Y, %H:%M")
    page.text(width - margin, 32, generated, 9, color=(224, 241, 229), align="right")
    page.text(
        width - margin,
        50,
        f"{data['shop'].currency}  ·  {data.get('note', '')}",
        9,
        color=(224, 241, 229),
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
        page.rect(margin, y - 6, total_width, 22, color=GREEN)
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
        page.rect(margin, y - 6, total_width, 22, color=(237, 246, 239))
        page.line(margin, y - 6, width - margin, y - 6, color=GREEN, width=1)
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
                    x + column_width - 6,
                    y,
                    text,
                    9.5,
                    bold=True,
                    color=GREEN_DARK,
                    align="right",
                )
            else:
                page.text(x + 6, y, text, 9.5, bold=True, color=GREEN_DARK)


def draw_footer(document: Document, data: dict, margin: int, width: int):
    page = document.page
    page.line(margin, 790, width - margin, 790, color=LINE)
    page.text(margin, 800, "SmSt Africa  ·  smst.africa", 8, color=MUTED)
    page.text(
        width - margin,
        800,
        f"Page {len(document.pages)}",
        8,
        color=MUTED,
        align="right",
    )


# ------------------------------------------------------------------ excel
def build_xlsx(run: FinanceReport, data: dict) -> bytes:
    workbook = Workbook(accent="FF2A8051", title_color="FF124F2E")
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
        for value in data["totals"]:
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                cells.append((value, STYLE_TOTAL_NUMBER))
            else:
                cells.append((value, STYLE_TOTAL))
        sheet.append(cells)

    return workbook.to_bytes()


# ----------------------------------------------------------------- build
def build_report(run: FinanceReport) -> FinanceReport:
    """Build the file for a report run and attach it to the record."""
    run.status = FinanceReport.RUNNING
    run.save(update_fields=["status"])

    try:
        data = collect(run)
        if run.format == FinanceReport.XLSX:
            content = build_xlsx(run, data)
            extension = "xlsx"
        else:
            content = build_pdf(run, data)
            extension = "pdf"

        slug = f"{run.shop.slug}-{run.kind}-{run.created_at:%Y%m%d-%H%M%S}.{extension}"
        run.filename = slug
        run.content = content
        run.status = FinanceReport.READY
        run.error = ""
        run.save(update_fields=["status", "error", "filename", "content"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not build the finance report")
        run.status = FinanceReport.FAILED
        run.error = str(exc)[:240]
        run.save(update_fields=["status", "error"])
        raise

    return run
