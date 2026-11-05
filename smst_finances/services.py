"""The rules of SmSt Finances.

Every entry is written through this module. An entry posts two or more lines
into the chart of accounts, so the ledger, the statements and the dashboard all
read the same numbers. Nothing in the app writes a JournalLine by hand.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from smst_stocks.models import Product, StockMovement

from .models import (
    FinanceAccount,
    FinanceBudget,
    FinanceChart,
    FinanceEntry,
    FinanceOption,
    JournalLine,
    ZERO,
)

logger = logging.getLogger("smst")


class FinanceError(Exception):
    """A rule was broken. The message is safe to show the user."""


# --------------------------------------------------------------- accounts
#: The chart of accounts every shop starts with.
DEFAULT_ACCOUNTS = (
    ("1000", "Cash", FinanceAccount.ASSET, "cash", "Money in the till."),
    ("1010", "Bank", FinanceAccount.ASSET, "bank", "Money in the bank."),
    (
        "1100",
        "Accounts Receivable",
        FinanceAccount.ASSET,
        "receivable",
        "Money customers still owe.",
    ),
    (
        "1200",
        "Inventory",
        FinanceAccount.ASSET,
        "inventory",
        "The cost of stock in hand.",
    ),
    (
        "2000",
        "Accounts Payable",
        FinanceAccount.LIABILITY,
        "payable",
        "Money the shop still owes.",
    ),
    (
        "2100",
        "Tax Payable",
        FinanceAccount.LIABILITY,
        "tax_payable",
        "Tax collected and not yet sent on.",
    ),
    (
        "3000",
        "Owner's Equity",
        FinanceAccount.EQUITY,
        "equity",
        "What the owner has put into the business.",
    ),
    (
        "4000",
        "Sales Revenue",
        FinanceAccount.INCOME,
        "sales",
        "Money earned from selling.",
    ),
    (
        "4100",
        "Other Income",
        FinanceAccount.INCOME,
        "other_income",
        "Profit and income outside ordinary sales.",
    ),
    (
        "5000",
        "Cost of Goods Sold",
        FinanceAccount.EXPENSE,
        "cogs",
        "What the goods that were sold cost.",
    ),
    (
        "6000",
        "Operating Expenses",
        FinanceAccount.EXPENSE,
        "operating",
        "The everyday cost of running the shop.",
    ),
    (
        "6100",
        "Transport and Delivery",
        FinanceAccount.EXPENSE,
        "transport",
        "Bike fares, fuel and deliveries.",
    ),
    (
        "6200",
        "Discounts Given",
        FinanceAccount.EXPENSE,
        "discounts",
        "What was taken off a price.",
    ),
    (
        "6300",
        "Returns and Refunds",
        FinanceAccount.EXPENSE,
        "returns",
        "Money given back to a customer.",
    ),
    (
        "6400",
        "Inventory Loss",
        FinanceAccount.EXPENSE,
        "loss",
        "Stock that was damaged, lost or stolen.",
    ),
    (
        "6500",
        "Tax Expense",
        FinanceAccount.EXPENSE,
        "tax_expense",
        "Tax the shop paid.",
    ),
)

ROLE_BY_CODE = {code: role for code, _name, _type, role, _desc in DEFAULT_ACCOUNTS}
ROLE_CODES = {role: code for code, _name, _type, role, _desc in DEFAULT_ACCOUNTS}

KIND_ROLE = {
    FinanceEntry.INCOME: "sales",
    FinanceEntry.PROFIT: "other_income",
    FinanceEntry.EXPENSE: "operating",
    FinanceEntry.LOSS: "loss",
    FinanceEntry.DISCOUNT: "discounts",
    FinanceEntry.REFUND: "returns",
    FinanceEntry.TAX: "tax_payable",
    FinanceEntry.ADJUSTMENT: "operating",
}

INCOME_KINDS = {FinanceEntry.INCOME, FinanceEntry.PROFIT}
EXPENSE_KINDS = {
    FinanceEntry.EXPENSE,
    FinanceEntry.LOSS,
    FinanceEntry.DISCOUNT,
    FinanceEntry.REFUND,
}


def _dec(value, default=ZERO) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation, ArithmeticError):
        return default


def _money(value) -> Decimal:
    return _dec(value).quantize(Decimal("0.01"))


def ensure_default_accounts(shop) -> dict:
    """Make sure the shop has the accounts the app expects.

    Returns a mapping of role to account. Existing accounts are left alone, so
    a shop can rename one without the app losing track of it.
    """
    existing = {
        account.code: account
        for account in FinanceAccount.objects.filter(shop=shop)
    }
    created = []
    for code, name, kind, _role, description in DEFAULT_ACCOUNTS:
        if code in existing:
            continue
        created.append(
            FinanceAccount(
                shop=shop,
                code=code,
                name=name,
                type=kind,
                description=description,
                is_system=True,
            )
        )
    if created:
        FinanceAccount.objects.bulk_create(created, ignore_conflicts=True)

    accounts = {
        account.code: account for account in FinanceAccount.objects.filter(shop=shop)
    }
    return {
        role: accounts[code] for code, _name, _type, role, _desc in DEFAULT_ACCOUNTS
        if code in accounts
    }


def default_account(shop, role: str) -> FinanceAccount:
    accounts = ensure_default_accounts(shop)
    account = accounts.get(role)
    if account:
        return account
    raise FinanceError("The chart of accounts could not be prepared.")


def account_balance(account: FinanceAccount) -> Decimal:
    totals = JournalLine.objects.filter(
        account=account, entry__status=FinanceEntry.POSTED
    ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
    debit = _dec(totals["debit"])
    credit = _dec(totals["credit"])
    if account.type in (FinanceAccount.ASSET, FinanceAccount.EXPENSE):
        return _money(debit - credit)
    return _money(credit - debit)


def account_balances(shop) -> dict:
    rows = (
        JournalLine.objects.filter(
            account__shop=shop, entry__status=FinanceEntry.POSTED
        )
        .values("account_id", "account__type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
    )
    balances = {}
    for row in rows:
        debit = _dec(row["debit"])
        credit = _dec(row["credit"])
        if row["account__type"] in (
            FinanceAccount.ASSET,
            FinanceAccount.EXPENSE,
        ):
            balances[row["account_id"]] = _money(debit - credit)
        else:
            balances[row["account_id"]] = _money(credit - debit)
    return balances


# ----------------------------------------------------------------- posting
def _validate_links(shop, product=None, movement=None, order=None):
    if product and product.shop_id != shop.id:
        raise FinanceError("That product belongs to another shop.")
    if movement:
        if movement.product.shop_id != shop.id:
            raise FinanceError("That stock movement belongs to another shop.")
        if product and movement.product_id != product.id:
            raise FinanceError("The movement and the product do not match.")
        product = movement.product
    if order:
        if order.shop_id != shop.id:
            raise FinanceError("That order belongs to another shop.")
        if not product:
            product = order.product
    return product


def _entry_amount(entry: FinanceEntry) -> Decimal:
    """The amount, filling it in from the movement where the shop expects it."""
    amount = _money(entry.amount)
    if amount > 0:
        return amount

    movement = entry.movement
    product = entry.product or (movement.product if movement else None)
    if not movement or not product:
        return amount

    quantity = abs(_dec(movement.quantity))
    if entry.kind == FinanceEntry.PROFIT:
        return _money(quantity * _dec(product.margin_value))
    if entry.kind == FinanceEntry.LOSS:
        return _money(quantity * _dec(product.buying_price))
    if entry.kind == FinanceEntry.INCOME:
        return _money(quantity * _dec(product.selling_price))
    if entry.kind == FinanceEntry.REFUND:
        return _money(quantity * _dec(product.selling_price))
    if entry.kind == FinanceEntry.EXPENSE:
        return _money(quantity * _dec(product.buying_price))
    return amount


def _option_tax(entry: FinanceEntry) -> Decimal:
    """The tax an entry carries through its finance option."""
    option = entry.option
    if option.rate_type == FinanceOption.PERCENTAGE_INCLUDED:
        return option.tax_for(entry.amount)
    return option.amount_for(entry.amount)


def post_entry(entry: FinanceEntry) -> FinanceEntry:
    """Write the balanced lines for an entry.

    The account on the entry is the income, expense, tax or balance account.
    The payment account is the cash or bank account. The direction follows the
    kind, which is what makes the statement totals trustworthy.
    """
    entry.lines.all().delete()
    if entry.status != FinanceEntry.POSTED:
        return entry

    shop = entry.shop
    amount = _entry_amount(entry)
    if amount <= 0:
        raise FinanceError(
            "Enter an amount, or link a stock movement the amount can come from."
        )
    entry.amount = amount

    option = entry.option if entry.option_id else None
    account = entry.account
    if (
        option
        and option.kind == FinanceOption.TAX
        and option.account_id
        and account
        and account.pk == option.account_id
    ):
        # The tax account belongs to the tax line, not to the money recorded.
        account = None
    if not account or account.shop_id != shop.id:
        account = default_account(shop, KIND_ROLE.get(entry.kind, "operating"))
    payment = entry.payment_account
    if not payment or payment.shop_id != shop.id:
        payment = default_account(shop, "cash")

    # Stock loss comes out of stock, not out of the till.
    if entry.kind == FinanceEntry.LOSS and entry.movement_id:
        payment = default_account(shop, "inventory")

    tax = ZERO
    if option and option.kind == FinanceOption.TAX and entry.kind != FinanceEntry.TAX:
        if option.rate_type == FinanceOption.PERCENTAGE_INCLUDED:
            tax = option.tax_for(amount)
            if tax >= amount:
                raise FinanceError("The tax is more than the amount.")
        else:
            tax = option.amount_for(amount)

    lines = []
    if entry.kind in (FinanceEntry.INCOME, FinanceEntry.PROFIT):
        if tax:
            tax_account = option.account or default_account(shop, "tax_payable")
            if option.rate_type == FinanceOption.PERCENTAGE_INCLUDED:
                lines = [
                    (payment, amount, ZERO),
                    (account, ZERO, amount - tax),
                    (tax_account, ZERO, tax),
                ]
            else:
                lines = [
                    (payment, amount + tax, ZERO),
                    (account, ZERO, amount),
                    (tax_account, ZERO, tax),
                ]
        else:
            lines = [(payment, amount, ZERO), (account, ZERO, amount)]
    elif entry.kind == FinanceEntry.TAX:
        if account.type in (
            FinanceAccount.LIABILITY,
            FinanceAccount.EQUITY,
            FinanceAccount.INCOME,
        ):
            lines = [(payment, amount, ZERO), (account, ZERO, amount)]
        else:
            lines = [(account, amount, ZERO), (payment, ZERO, amount)]
    elif entry.kind == FinanceEntry.ADJUSTMENT:
        if account.type in (
            FinanceAccount.LIABILITY,
            FinanceAccount.EQUITY,
            FinanceAccount.INCOME,
        ):
            lines = [(payment, amount, ZERO), (account, ZERO, amount)]
        else:
            lines = [(account, amount, ZERO), (payment, ZERO, amount)]
    else:
        if tax:
            tax_account = option.account or default_account(shop, "tax_payable")
            if option.rate_type == FinanceOption.PERCENTAGE_INCLUDED:
                lines = [
                    (account, amount - tax, ZERO),
                    (tax_account, tax, ZERO),
                    (payment, ZERO, amount),
                ]
            else:
                lines = [
                    (account, amount, ZERO),
                    (tax_account, tax, ZERO),
                    (payment, ZERO, amount + tax),
                ]
        else:
            lines = [(account, amount, ZERO), (payment, ZERO, amount)]

    JournalLine.objects.bulk_create(
        [
            JournalLine(
                entry=entry,
                account=line_account,
                debit=debit,
                credit=credit,
                description=entry.description,
            )
            for line_account, debit, credit in lines
        ]
    )

    debit = sum((line[1] for line in lines), ZERO)
    credit = sum((line[2] for line in lines), ZERO)
    if debit != credit:
        raise FinanceError("The entry did not balance.")

    entry.save(update_fields=["amount", "updated_at"])
    return entry


# -------------------------------------------------------------- entries
@transaction.atomic
def create_entry(shop, data: dict, user=None) -> FinanceEntry:
    """Create an entry from what the shopkeeper sent, then post it."""
    option = data.get("option")
    if option and option.shop_id != shop.id:
        raise FinanceError("That finance option belongs to another shop.")

    product = _validate_links(
        shop,
        product=data.get("product"),
        movement=data.get("movement"),
        order=data.get("order"),
    )
    movement = data.get("movement")
    order = data.get("order")

    kind = data.get("kind") or FinanceEntry.EXPENSE
    if kind not in {choice[0] for choice in FinanceEntry.KIND_CHOICES}:
        raise FinanceError("Choose a kind of entry.")

    base_amount = data.get("base_amount")
    base_amount = _money(base_amount) if base_amount not in (None, "") else None
    amount = _money(data.get("amount"))
    rate = data.get("rate")
    rate = _dec(rate) if rate not in (None, "") else None

    if option and rate is None:
        rate = _dec(option.rate)
    # A tax option rides on top of the money recorded; it does not set it.
    if option and option.kind != FinanceOption.TAX:
        if amount <= 0 and base_amount is not None:
            amount = option.amount_for(base_amount)
        if base_amount is None and option.rate_type == FinanceOption.FIXED:
            amount = amount or _money(option.rate)

    status = data.get("status") or FinanceEntry.POSTED
    if status not in {choice[0] for choice in FinanceEntry.STATUS_CHOICES}:
        raise FinanceError("That is not a status an entry can hold.")

    description = (data.get("description") or "").strip()
    if not description and option:
        description = option.name
    if not description and movement:
        description = movement.get_kind_display()
    if not description:
        raise FinanceError("Say what the entry was for.")

    account = data.get("account")
    if account and account.shop_id != shop.id:
        raise FinanceError("That account belongs to another shop.")
    if not account and option and option.account_id and option.kind != FinanceOption.TAX:
        account = option.account

    payment_account = data.get("payment_account")
    if payment_account and payment_account.shop_id != shop.id:
        raise FinanceError("That payment account belongs to another shop.")
    if not payment_account:
        payment_account = default_account(shop, "cash")

    entry = FinanceEntry(
        shop=shop,
        option=option,
        product=product,
        movement=movement,
        order=order,
        account=account,
        payment_account=payment_account,
        kind=kind,
        status=status,
        source=(
            FinanceEntry.STOCK
            if movement
            else FinanceEntry.ORDER
            if order
            else FinanceEntry.MANUAL
        ),
        amount=amount,
        base_amount=base_amount,
        rate=rate,
        description=description,
        note=(data.get("note") or "").strip(),
        occurred_at=data.get("occurred_at") or timezone.now(),
        created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
    )
    entry.save()
    post_entry(entry)
    return entry


@transaction.atomic
def update_entry(entry: FinanceEntry, data: dict) -> FinanceEntry:
    """Change an entry and repost it, so the books never keep an old figure."""
    if entry.status == FinanceEntry.VOID:
        raise FinanceError("A void entry cannot be changed.")

    option = data.get("option", entry.option)
    if option and option.shop_id != entry.shop_id:
        raise FinanceError("That finance option belongs to another shop.")

    product = data.get("product", entry.product)
    movement = data.get("movement", entry.movement)
    order = data.get("order", entry.order)
    product = _validate_links(
        entry.shop, product=product, movement=movement, order=order
    )

    entry.option = option
    entry.product = product
    entry.movement = movement
    entry.order = order
    entry.source = (
        FinanceEntry.STOCK
        if movement
        else FinanceEntry.ORDER
        if order
        else FinanceEntry.MANUAL
    )

    if "kind" in data:
        if data["kind"] not in {choice[0] for choice in FinanceEntry.KIND_CHOICES}:
            raise FinanceError("Choose a kind of entry.")
        entry.kind = data["kind"]
    if "description" in data:
        entry.description = (data.get("description") or "").strip()
    if "note" in data:
        entry.note = (data.get("note") or "").strip()
    if "occurred_at" in data and data.get("occurred_at"):
        entry.occurred_at = data["occurred_at"]
    if "status" in data:
        if data["status"] not in {choice[0] for choice in FinanceEntry.STATUS_CHOICES}:
            raise FinanceError("That is not a status an entry can hold.")
        entry.status = data["status"]

    if "account" in data and data.get("account"):
        account = data["account"]
        if account.shop_id != entry.shop_id:
            raise FinanceError("That account belongs to another shop.")
        entry.account = account
    if "payment_account" in data and data.get("payment_account"):
        payment = data["payment_account"]
        if payment.shop_id != entry.shop_id:
            raise FinanceError("That payment account belongs to another shop.")
        entry.payment_account = payment

    if "base_amount" in data:
        value = data.get("base_amount")
        entry.base_amount = _money(value) if value not in (None, "") else None
    if "rate" in data:
        value = data.get("rate")
        entry.rate = _dec(value) if value not in (None, "") else None
    if "amount" in data:
        entry.amount = _money(data.get("amount"))
    elif entry.option and entry.base_amount is not None:
        entry.amount = entry.option.amount_for(entry.base_amount)
        entry.rate = entry.option.rate

    if not entry.description:
        raise FinanceError("Say what the entry was for.")

    entry.save()
    post_entry(entry)
    return entry


@transaction.atomic
def void_entry(entry: FinanceEntry) -> FinanceEntry:
    entry.status = FinanceEntry.VOID
    entry.save(update_fields=["status", "updated_at"])
    entry.lines.all().delete()
    return entry


@transaction.atomic
def delete_entry(entry: FinanceEntry) -> None:
    entry.delete()


# ------------------------------------------------------------- summaries
def _range(start=None, end=None):
    if end is None:
        end = timezone.localdate()
    if start is None:
        start = end.replace(day=1)
    return start, end


def _entries(shop, start=None, end=None):
    start, end = _range(start, end)
    return FinanceEntry.objects.filter(
        shop=shop,
        status=FinanceEntry.POSTED,
        occurred_at__date__gte=start,
        occurred_at__date__lte=end,
    )


def entry_summary(shop, start=None, end=None) -> dict:
    entries = _entries(shop, start, end)
    income = (
        entries.filter(kind__in=INCOME_KINDS).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    expense = (
        entries.filter(kind__in=EXPENSE_KINDS)
        .aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    tax = (
        entries.filter(kind=FinanceEntry.TAX).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    # Tax carried inside a sale or bill rides with that entry, not its own one.
    tax += sum(
        (
            _option_tax(entry) if entry.kind in INCOME_KINDS else -_option_tax(entry)
            for entry in entries.filter(option__kind=FinanceOption.TAX)
            .exclude(kind=FinanceEntry.TAX)
            .select_related("option")
        ),
        ZERO,
    )
    discount = (
        entries.filter(kind=FinanceEntry.DISCOUNT)
        .aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    profit = (
        entries.filter(kind=FinanceEntry.PROFIT)
        .aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    loss = (
        entries.filter(kind=FinanceEntry.LOSS)
        .aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    income = _money(income)
    expense = _money(expense)
    tax = _money(tax)
    return {
        "income": income,
        "expense": expense,
        "tax": tax,
        "discount": _money(discount),
        "profit": _money(profit),
        "loss": _money(loss),
        "net": _money(income - expense - tax),
        "count": entries.count(),
        "start": start,
        "end": end,
    }


def stock_summary(shop) -> dict:
    products = Product.objects.filter(shop=shop)
    rows = products.aggregate(
        quantity=Sum("quantity"),
    )
    stock_amount = sum(
        (_dec(product.quantity) * _dec(product.selling_price) for product in products),
        ZERO,
    )
    stock_cost = sum(
        (_dec(product.quantity) * _dec(product.buying_price) for product in products),
        ZERO,
    )
    return {
        "products": products.count(),
        "quantity": _money(rows["quantity"]),
        "stock_amount": _money(stock_amount),
        "stock_cost": _money(stock_cost),
        "margin": _money(stock_amount - stock_cost),
    }


def dashboard_summary(shop, start=None, end=None) -> dict:
    summary = entry_summary(shop, start, end)
    balances = account_balances(shop)
    accounts = {account.code: account for account in FinanceAccount.objects.filter(shop=shop)}
    cash = sum(
        (
            balances.get(accounts[code].id, ZERO)
            for code in ("1000", "1010")
            if code in accounts
        ),
        ZERO,
    )
    receivable = (
        balances.get(accounts["1100"].id, ZERO) if "1100" in accounts else ZERO
    )
    payable = balances.get(accounts["2000"].id, ZERO) if "2000" in accounts else ZERO
    tax_due = balances.get(accounts["2100"].id, ZERO) if "2100" in accounts else ZERO
    stock = stock_summary(shop)
    summary.update(
        {
            "cash": _money(cash),
            "receivable": _money(receivable),
            "payable": _money(payable),
            "tax_due": _money(tax_due),
            "stock_amount": stock["stock_amount"],
            "stock_cost": stock["stock_cost"],
            "stock_quantity": stock["quantity"],
            "products": stock["products"],
            "budget_count": FinanceBudget.objects.filter(shop=shop).count(),
        }
    )
    return summary


# ------------------------------------------------------------ statements
def trial_balance(shop, start=None, end=None) -> dict:
    start, end = _range(start, end)
    rows = (
        JournalLine.objects.filter(
            entry__shop=shop,
            entry__status=FinanceEntry.POSTED,
            account__shop=shop,
            entry__occurred_at__date__gte=start,
            entry__occurred_at__date__lte=end,
        )
        .values("account_id", "account__code", "account__name", "account__type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )
    data = []
    total_debit = ZERO
    total_credit = ZERO
    for row in rows:
        debit = _money(row["debit"])
        credit = _money(row["credit"])
        if debit == 0 and credit == 0:
            continue
        total_debit += debit
        total_credit += credit
        data.append(
            {
                "account": row["account_id"],
                "code": row["account__code"],
                "name": row["account__name"],
                "type": row["account__type"],
                "debit": debit,
                "credit": credit,
                "balance": _money(debit - credit),
            }
        )
    return {
        "kind": "trial_balance",
        "title": "Trial balance",
        "start": start,
        "end": end,
        "rows": data,
        "total_debit": _money(total_debit),
        "total_credit": _money(total_credit),
        "balanced": total_debit == total_credit,
    }


def profit_and_loss(shop, start=None, end=None) -> dict:
    start, end = _range(start, end)
    rows = (
        JournalLine.objects.filter(
            entry__shop=shop,
            entry__status=FinanceEntry.POSTED,
            account__shop=shop,
            entry__occurred_at__date__gte=start,
            entry__occurred_at__date__lte=end,
            account__type__in=(FinanceAccount.INCOME, FinanceAccount.EXPENSE),
        )
        .values("account_id", "account__code", "account__name", "account__type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )
    income = []
    expense = []
    for row in rows:
        debit = _money(row["debit"])
        credit = _money(row["credit"])
        if row["account__type"] == FinanceAccount.INCOME:
            amount = _money(credit - debit)
            if amount:
                income.append(
                    {
                        "account": row["account_id"],
                        "code": row["account__code"],
                        "name": row["account__name"],
                        "amount": amount,
                    }
                )
        else:
            amount = _money(debit - credit)
            if amount:
                expense.append(
                    {
                        "account": row["account_id"],
                        "code": row["account__code"],
                        "name": row["account__name"],
                        "amount": amount,
                    }
                )
    income_total = sum((row["amount"] for row in income), ZERO)
    expense_total = sum((row["amount"] for row in expense), ZERO)
    return {
        "kind": "profit_loss",
        "title": "Profit and loss",
        "start": start,
        "end": end,
        "income": income,
        "expense": expense,
        "income_total": _money(income_total),
        "expense_total": _money(expense_total),
        "net": _money(income_total - expense_total),
    }


def balance_sheet(shop, start=None, end=None) -> dict:
    start, end = _range(start, end)
    rows = (
        JournalLine.objects.filter(
            entry__shop=shop,
            entry__status=FinanceEntry.POSTED,
            account__shop=shop,
            entry__occurred_at__date__lte=end,
        )
        .values("account_id", "account__code", "account__name", "account__type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )
    assets, liabilities, equity = [], [], []
    for row in rows:
        debit = _money(row["debit"])
        credit = _money(row["credit"])
        if row["account__type"] == FinanceAccount.ASSET:
            amount = _money(debit - credit)
            if amount:
                assets.append(
                    {
                        "account": row["account_id"],
                        "code": row["account__code"],
                        "name": row["account__name"],
                        "amount": amount,
                    }
                )
        elif row["account__type"] == FinanceAccount.LIABILITY:
            amount = _money(credit - debit)
            if amount:
                liabilities.append(
                    {
                        "account": row["account_id"],
                        "code": row["account__code"],
                        "name": row["account__name"],
                        "amount": amount,
                    }
                )
        elif row["account__type"] == FinanceAccount.EQUITY:
            amount = _money(credit - debit)
            if amount:
                equity.append(
                    {
                        "account": row["account_id"],
                        "code": row["account__code"],
                        "name": row["account__name"],
                        "amount": amount,
                    }
                )

    # Everything earned and not withdrawn belongs to the owner at the end.
    pnl = profit_and_loss(shop, start=None, end=end)
    if pnl["net"]:
        equity.append(
            {
                "account": 0,
                "code": "3900",
                "name": "Current earnings",
                "amount": pnl["net"],
            }
        )

    assets_total = sum((row["amount"] for row in assets), ZERO)
    liabilities_total = sum((row["amount"] for row in liabilities), ZERO)
    equity_total = sum((row["amount"] for row in equity), ZERO)
    return {
        "kind": "balance_sheet",
        "title": "Balance sheet",
        "start": start,
        "end": end,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "assets_total": _money(assets_total),
        "liabilities_total": _money(liabilities_total),
        "equity_total": _money(equity_total),
        "balanced": _money(assets_total)
        == _money(liabilities_total + equity_total),
    }


def cash_flow(shop, start=None, end=None) -> dict:
    start, end = _range(start, end)
    cash_ids = list(
        FinanceAccount.objects.filter(
            shop=shop, code__in=("1000", "1010")
        ).values_list("id", flat=True)
    )
    lines = (
        JournalLine.objects.filter(
            entry__shop=shop,
            entry__status=FinanceEntry.POSTED,
            account_id__in=cash_ids,
            entry__occurred_at__date__gte=start,
            entry__occurred_at__date__lte=end,
        )
        .select_related("entry", "account")
        .order_by("entry__occurred_at", "id")
    )
    rows = []
    inflow_total = ZERO
    outflow_total = ZERO
    for line in lines:
        inflow = _money(line.debit)
        outflow = _money(line.credit)
        inflow_total += inflow
        outflow_total += outflow
        rows.append(
            {
                "date": line.entry.occurred_at,
                "reference": line.entry.reference,
                "description": line.entry.description,
                "account": line.account.name,
                "inflow": inflow,
                "outflow": outflow,
                "net": _money(inflow - outflow),
            }
        )
    return {
        "kind": "cash_flow",
        "title": "Cash flow",
        "start": start,
        "end": end,
        "rows": rows,
        "inflow_total": _money(inflow_total),
        "outflow_total": _money(outflow_total),
        "net": _money(inflow_total - outflow_total),
    }


def general_ledger(shop, start=None, end=None) -> dict:
    start, end = _range(start, end)
    entries = (
        FinanceEntry.objects.filter(
            shop=shop,
            status=FinanceEntry.POSTED,
            occurred_at__date__gte=start,
            occurred_at__date__lte=end,
        )
        .select_related("option", "account", "payment_account", "product", "movement")
        .prefetch_related("lines__account")
        .order_by("occurred_at", "id")
    )
    return {
        "kind": "general_ledger",
        "title": "General ledger",
        "start": start,
        "end": end,
        "rows": entries,
    }


# ---------------------------------------------------------------- budgets
def budget_status(budget: FinanceBudget) -> dict:
    today = timezone.localdate()
    start = budget.starts_on or today.replace(day=1)
    end = budget.ends_on or today
    if budget.period == FinanceBudget.MONTHLY:
        start = max(start, today.replace(day=1))
        end = min(end, today.replace(day=28) + timedelta(days=4))
        end = end.replace(day=1) - timedelta(days=1)
        if end < today:
            end = today
    elif budget.period == FinanceBudget.QUARTERLY:
        quarter = (today.month - 1) // 3
        start = today.replace(month=quarter * 3 + 1, day=1)
        end = (start + timedelta(days=95)).replace(day=1) - timedelta(days=1)
        if end < today:
            end = today
    elif budget.period == FinanceBudget.YEARLY:
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)

    entries = FinanceEntry.objects.filter(
        shop=budget.shop,
        status=FinanceEntry.POSTED,
        occurred_at__date__gte=start,
        occurred_at__date__lte=end,
    )
    if budget.option_id:
        entries = entries.filter(option_id=budget.option_id)
    spent = ZERO
    if budget.account_id:
        totals = JournalLine.objects.filter(
            entry__in=entries, account_id=budget.account_id
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        account = budget.account
        if account and account.type in (FinanceAccount.ASSET, FinanceAccount.EXPENSE):
            spent = _money(_dec(totals["debit"]) - _dec(totals["credit"]))
        else:
            spent = _money(_dec(totals["credit"]) - _dec(totals["debit"]))
    else:
        spent = _money(
            entries.aggregate(total=Sum("amount"))["total"] or ZERO
        )
    amount = _money(budget.amount)
    remaining = _money(amount - spent)
    percent = 0
    if amount > 0:
        percent = min(999, round(float(spent / amount) * 100, 1))
    return {
        "start": start,
        "end": end,
        "spent": spent,
        "remaining": remaining,
        "percent": percent,
    }


# ----------------------------------------------------------------- charts
def _as_date(value, default=None):
    if not value:
        return default
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _stock_metric(shop, metric, at=None) -> Decimal:
    products = Product.objects.filter(shop=shop)
    total = ZERO
    for product in products:
        quantity = _dec(product.quantity)
        if at is not None:
            after = (
                StockMovement.objects.filter(
                    product=product, created_at__date__gt=at
                ).aggregate(total=Sum("quantity"))["total"]
                or ZERO
            )
            quantity -= _dec(after)
        if metric == FinanceChart.STOCK_QUANTITY:
            total += quantity
        elif metric == FinanceChart.STOCK_COST:
            total += quantity * _dec(product.buying_price)
        elif metric == FinanceChart.MARGIN:
            total += quantity * _dec(product.margin_value)
        else:
            total += quantity * _dec(product.selling_price)
    return _money(total)


def _metric_value(entry: FinanceEntry, metric: str) -> Decimal:
    if metric == FinanceChart.COUNT:
        return Decimal("1")
    if metric == FinanceChart.AMOUNT:
        return _money(entry.amount)
    if metric == FinanceChart.INCOME:
        return _money(entry.amount) if entry.kind in INCOME_KINDS else ZERO
    if metric == FinanceChart.EXPENSE:
        return _money(entry.amount) if entry.kind in EXPENSE_KINDS else ZERO
    if metric == FinanceChart.NET:
        if entry.kind in INCOME_KINDS:
            return _money(entry.amount)
        if entry.kind in EXPENSE_KINDS or entry.kind == FinanceEntry.TAX:
            return -_money(entry.amount)
        return ZERO
    if metric == FinanceChart.TAX:
        return _money(entry.amount) if entry.kind == FinanceEntry.TAX else ZERO
    if metric == FinanceChart.DISCOUNT:
        return _money(entry.amount) if entry.kind == FinanceEntry.DISCOUNT else ZERO
    if metric == FinanceChart.PROFIT:
        return _money(entry.amount) if entry.kind == FinanceEntry.PROFIT else ZERO
    if metric == FinanceChart.LOSS:
        return _money(entry.amount) if entry.kind == FinanceEntry.LOSS else ZERO
    if metric == FinanceChart.QUANTITY:
        return abs(_dec(entry.movement.quantity)) if entry.movement_id else ZERO
    return _money(entry.amount)


def chart_data(
    shop,
    x_source=FinanceChart.TIME,
    y_source=FinanceChart.INCOME,
    x_values=None,
    y_values=None,
    date_from=None,
    date_to=None,
) -> dict:
    """Build the two sides of a graph separately.

    Either send ``x_values`` and ``y_values`` to plot the numbers exactly as
    they were typed, or choose a source for each axis. The example the app was
    asked for, stock amount on Y and time on X, is served by
    ``x_source=time`` and ``y_source=stock_amount``.
    """
    x_values = list(x_values or [])
    y_values = list(y_values or [])
    if x_values or y_values:
        labels = [str(value) for value in x_values]
        values = [_dec(value) for value in y_values]
        size = min(len(labels), len(values))
        return {
            "labels": labels[:size],
            "values": [_money(value) for value in values[:size]],
            "x_source": FinanceChart.CUSTOM,
            "y_source": FinanceChart.CUSTOM,
        }

    end = _as_date(date_to, timezone.localdate())
    start = _as_date(date_from, end - timedelta(days=29))
    if start > end:
        start, end = end, start

    if x_source == FinanceChart.TIME:
        days = (end - start).days + 1
        days = min(max(days, 1), 120)
        labels = [start + timedelta(days=index) for index in range(days)]
        if y_source in (
            FinanceChart.STOCK_AMOUNT,
            FinanceChart.STOCK_QUANTITY,
            FinanceChart.STOCK_COST,
            FinanceChart.MARGIN,
        ):
            values = [_stock_metric(shop, y_source, at=day) for day in labels]
        else:
            entries = list(_entries(shop, start, end).select_related("movement"))
            buckets = {day: ZERO for day in labels}
            for entry in entries:
                day = timezone.localtime(entry.occurred_at).date()
                if day in buckets:
                    buckets[day] += _metric_value(entry, y_source)
            values = [buckets[day] for day in labels]
        return {
            "labels": [day.isoformat() for day in labels],
            "values": [_money(value) for value in values],
            "x_source": x_source,
            "y_source": y_source,
        }

    if y_source in (
        FinanceChart.STOCK_AMOUNT,
        FinanceChart.STOCK_QUANTITY,
        FinanceChart.STOCK_COST,
        FinanceChart.MARGIN,
    ):
        products = Product.objects.filter(shop=shop).order_by("name")
        if x_source == FinanceChart.CATEGORY:
            groups = {}
            for product in products:
                key = product.category or "Uncategorised"
                quantity = _dec(product.quantity)
                if y_source == FinanceChart.STOCK_QUANTITY:
                    value = quantity
                elif y_source == FinanceChart.STOCK_COST:
                    value = quantity * _dec(product.buying_price)
                elif y_source == FinanceChart.MARGIN:
                    value = quantity * _dec(product.margin_value)
                else:
                    value = quantity * _dec(product.selling_price)
                groups[key] = groups.get(key, ZERO) + value
            labels = list(groups.keys())
            values = [groups[label] for label in labels]
        else:
            labels = [product.name for product in products]
            values = []
            for product in products:
                quantity = _dec(product.quantity)
                if y_source == FinanceChart.STOCK_QUANTITY:
                    value = quantity
                elif y_source == FinanceChart.STOCK_COST:
                    value = quantity * _dec(product.buying_price)
                elif y_source == FinanceChart.MARGIN:
                    value = quantity * _dec(product.margin_value)
                else:
                    value = quantity * _dec(product.selling_price)
                values.append(value)
        return {
            "labels": labels,
            "values": [_money(value) for value in values],
            "x_source": x_source,
            "y_source": y_source,
        }

    entries = list(
        _entries(shop, start, end).select_related(
            "movement", "product", "option", "account"
        )
    )
    groups = {}
    for entry in entries:
        if x_source == FinanceChart.OPTION:
            key = entry.option.name if entry.option else "No option"
        elif x_source == FinanceChart.ACCOUNT:
            key = entry.account.name if entry.account else "No account"
        elif x_source == FinanceChart.KIND:
            key = entry.get_kind_display()
        elif x_source == FinanceChart.PRODUCT:
            key = entry.product.name if entry.product else "No product"
        elif x_source == FinanceChart.CATEGORY:
            key = (
                entry.product.category
                if entry.product and entry.product.category
                else "Uncategorised"
            )
        else:
            key = entry.kind
        groups[key] = groups.get(key, ZERO) + _metric_value(entry, y_source)

    ordered = sorted(groups.items(), key=lambda item: item[0])
    return {
        "labels": [label for label, _value in ordered],
        "values": [_money(value) for _label, value in ordered],
        "x_source": x_source,
        "y_source": y_source,
    }


# ------------------------------------------------------------------ stock
def link_stock_movement(shop, movement_id, kind, user=None, **extra):
    """A shortcut for putting a money figure against a stock movement.

    Used by the app and available to other SmSt apps: a sale can carry its
    profit, a loss can carry the cost of the damaged item.
    """
    movement = StockMovement.objects.select_related("product").filter(
        pk=movement_id, product__shop=shop
    ).first()
    if not movement:
        raise FinanceError("That stock movement is not in this shop.")
    data = {
        "movement": movement,
        "product": movement.product,
        "kind": kind,
        "description": extra.pop(
            "description",
            f"{movement.get_kind_display()} — {movement.product.name}",
        ),
        **extra,
    }
    return create_entry(shop, data, user=user)


# ------------------------------------------------------- stock integration
#: The finance kind that follows each kind of stock movement.
MOVEMENT_FINANCE_KIND = {
    StockMovement.SALE: FinanceEntry.INCOME,
    StockMovement.DELIVERY: FinanceEntry.EXPENSE,
    StockMovement.RETURN: FinanceEntry.REFUND,
    StockMovement.LOSS: FinanceEntry.LOSS,
    StockMovement.OPENING: FinanceEntry.EXPENSE,
}

#: The account the other side of a stock movement lands in.
MOVEMENT_FINANCE_ROLE = {
    StockMovement.SALE: "sales",
    StockMovement.DELIVERY: "inventory",
    StockMovement.RETURN: "returns",
    StockMovement.LOSS: "loss",
    StockMovement.OPENING: "inventory",
}


def money_accounts(shop):
    """The accounts a stock movement can settle through, cash first.

    Only asset accounts make sense here: cash, the bank, receivables and stock
    itself. The list is what the movement form offers the shopkeeper.
    """
    ensure_default_accounts(shop)
    return list(
        FinanceAccount.objects.filter(
            shop=shop, type=FinanceAccount.ASSET, is_active=True
        ).order_by("code")
    )


def _movement_finance_kind(movement):
    if movement.kind == StockMovement.ADJUSTMENT:
        return (
            FinanceEntry.EXPENSE
            if movement.quantity > 0
            else FinanceEntry.LOSS
        )
    return MOVEMENT_FINANCE_KIND.get(movement.kind)


def _movement_finance_role(movement):
    if movement.kind == StockMovement.ADJUSTMENT:
        return "inventory" if movement.quantity > 0 else "loss"
    return MOVEMENT_FINANCE_ROLE.get(movement.kind)


def _movement_finance_amount(movement, kind):
    """What the movement is worth, using the cost the movement recorded."""
    quantity = abs(_dec(movement.quantity))
    product = movement.product
    if kind in (FinanceEntry.INCOME, FinanceEntry.REFUND):
        price = _dec(product.selling_price)
    elif movement.unit_cost is not None:
        price = _dec(movement.unit_cost)
    else:
        price = _dec(product.buying_price)
    return _money(quantity * price)


@transaction.atomic
def sync_stock_movement(movement, account=None, user=None):
    """Post (or refresh) the finance entry that follows a stock movement.

    A sale brings money in through the account the shopkeeper chose, a
    delivery takes money out of it. A loss is always posted, because the value
    leaves stock even when no cash moves. Returns the entry, or ``None`` when
    the movement was never a money movement.
    """
    kind = _movement_finance_kind(movement)
    if kind is None:
        return None

    account_id = getattr(account, "pk", account)
    if kind != FinanceEntry.LOSS and account_id in (None, ""):
        return None

    shop = movement.product.shop
    accounts = ensure_default_accounts(shop)

    money_account = None
    if account_id not in (None, ""):
        money_account = FinanceAccount.objects.filter(
            pk=account_id, shop=shop, type=FinanceAccount.ASSET
        ).first()
        if money_account is None:
            raise FinanceError(
                "Choose an asset account of this shop to save the money in."
            )

    role = _movement_finance_role(movement)
    ledger_account = accounts.get(role) or default_account(shop, role)
    if kind == FinanceEntry.LOSS:
        payment = accounts.get("inventory") or default_account(shop, "inventory")
    else:
        payment = money_account or accounts.get("cash") or default_account(shop, "cash")

    amount = _movement_finance_amount(movement, kind)
    description = f"{movement.get_kind_display()} — {movement.product.name}"
    data = {
        "kind": kind,
        "account": ledger_account,
        "payment_account": payment,
        "amount": amount,
        "description": description,
        "note": movement.note or "",
        "occurred_at": movement.created_at,
        "product": movement.product,
        "movement": movement,
    }

    entry = FinanceEntry.objects.filter(movement=movement).first()
    if entry:
        if entry.status == FinanceEntry.VOID:
            entry.status = FinanceEntry.POSTED
            entry.save(update_fields=["status", "updated_at"])
        entry = update_entry(entry, data)
        event = "finance.entry.updated"
    else:
        entry = create_entry(shop, data, user=user)
        event = "finance.entry.created"

    # Tell the finance dashboard after the stock write has committed, so the
    # summary it reads already includes this entry.
    from .realtime import broadcast_entry

    transaction.on_commit(lambda: broadcast_entry(entry, event))
    return entry


def movement_finance_payload(movement):
    """A small, JSON-safe view of the entry a movement produced."""
    entry = (
        FinanceEntry.objects.filter(movement=movement)
        .select_related("account", "payment_account")
        .first()
    )
    if not entry:
        return None
    return {
        "id": entry.id,
        "reference": entry.reference,
        "kind": entry.kind,
        "kind_label": entry.get_kind_display(),
        "amount": str(entry.amount),
        "account": entry.account.name if entry.account else "",
        "payment_account": (
            entry.payment_account.name if entry.payment_account else ""
        ),
        "status": entry.status,
    }
