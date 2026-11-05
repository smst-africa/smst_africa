# SmSt Finances

The money app of SmSt: the book behind the counter. It holds what came in and
what went out, the taxes and discounts a shop applies, the expenses, the chart
of accounts, the statements, and the graphs a shopkeeper draws for themselves.

The app opens on `/smst_finances/` on the app host.

```
https://app.smartstock.africa/smst_finances/
```

## What it does

- **Entries.** Every money event is one entry: a sale, a bill, a tax, a discount,
  a loss, a refund or an adjustment. Each entry posts a balanced pair of lines
  into the chart of accounts, so the screen, the statements and the reports can
  never disagree.
- **Finance options.** A tax rate, a discount, a delivery fee or any other rule
  the shop uses, fixed or a percentage. An option can be applied to a sale, a
  purchase, a stock movement or an expense, and it can carry the account it
  belongs to.
- **Linked to stock, automatically.** A movement in SmSt Stocks posts itself
  into the book: a sale is money in, a delivery is money out, a customer return
  is a refund, and a loss writes its cost off stock. The movement form asks
  which account the money moved through, so the cash, bank or receivable
  balance is right the moment the movement is recorded. Entries can also point
  at a product and a stock movement by hand. The two apps never tell the same
  story twice.
- **The chart of accounts.** Every shop starts with a working chart (cash, bank,
  receivables, inventory, payables, tax payable, equity, sales, cost of goods,
  operating expenses and more). Accounts can be renamed and added to; the
  built-ins keep their code so the app never loses track of them.
- **Statements.** Profit and loss, balance sheet, trial balance, cash flow and
  the general ledger, all read straight from the posted lines.
- **Budgets.** A plan for a month, a quarter or a year, measured against the
  book, with spends, what is left and how much of the plan is used.
- **Graphs.** A builder that picks the X and the Y separately: time, product,
  category, finance option, account or entry kind on one axis; income, expense,
  profit, loss, tax, discount, stock value, stock cost, margin, entry count or
  figures typed by hand on the other.
- **Reports.** Income, expenses, profit and loss, tax, cash flow, trial balance,
  balance sheet, the general ledger and the budgets, as a PDF or a spreadsheet.
- **Live updates.** A websocket keeps the dashboard up to date as the book moves.

## The API

Everything the app does goes through the API, under `/smst_finances/api/`.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` `POST` | `accounts/` | The chart of accounts, and a new account |
| `PATCH` `DELETE` | `accounts/<id>/` | Change an account, or remove one with no entries |
| `GET` `POST` | `options/` | The finance options, and a new one |
| `PATCH` `DELETE` | `options/<id>/` | Change and remove an option |
| `GET` `POST` | `entries/` | The book, and a new entry |
| `PATCH` `DELETE` | `entries/<id>/` | Change and remove an entry |
| `POST` | `entries/<id>/void/` | Void an entry and clear its lines |
| `GET` `POST` | `budgets/` | The spending plans, and a new one |
| `PATCH` `DELETE` | `budgets/<id>/` | Change and remove a budget |
| `GET` `POST` | `charts/` | The saved graphs, and a new one |
| `PATCH` `DELETE` | `charts/<id>/` | Change and remove a graph |
| `POST` | `charts/preview/` | Draw a graph without saving it |
| `GET` `POST` | `reports/` | The reports, and a request for a new one |
| `GET` | `reports/<id>/download/` | The file a report produced |
| `GET` | `summary/` | The dashboard totals for the shop |
| `GET` | `statements/` | Any statement, chosen with `?kind=` |

An entry is written with the amount the shopkeeper typed, or with a stock
movement the amount can be worked out from: a sale of 3 at a margin of 19
carries 57, and a loss of 2 costing 149 carries 298. The kind decides which way
the money moves, which is what makes the statement totals trustworthy.

## The websocket

```
ws://<host>/ws/smst_finances/shop/     the dashboard of the signed in user
```

Messages look like this:

```json
{"event": "finance.entry.created", "data": {"id": 14, "reference": "FN-9C21A0", "kind": "income", "amount": 504.0, "summary": {"income": 504.0, "expense": 0.0, "net": 504.0, "cash": 504.0}}}
```

`finance.entry.updated`, `finance.entry.voided`, `finance.option.updated`,
`finance.account.created`, `finance.budget.created`, `finance.chart.created` and
`report.ready` are sent the same way.

## Background work

| Task | What it does |
| --- | --- |
| `smst_finances.tasks.generate_report` | Builds a report and tells the shop it is ready |
| `smst_finances.tasks.finance_daily_digest` | A short money digest for every shop |
| `smst_finances.tasks.budget_alerts` | Tells the owner when a budget is 80% used or over |

The digest and the alerts are meant to run on a schedule. Add them to the celery
beat schedule in your settings:

```python
CELERY_BEAT_SCHEDULE = {
    "smst-finances-daily-digest": {
        "task": "smst_finances.tasks.finance_daily_digest",
        "schedule": 60.0 * 60 * 7,
    },
    "smst-finances-budget-alerts": {
        "task": "smst_finances.tasks.budget_alerts",
        "schedule": 60.0 * 60 * 12,
    },
}
```

## Reports

The PDF and the spreadsheet are written by hand, in `core/reports/`, so the app
carries no reporting library. `core/reports/pdf.py` writes a PDF and
`core/reports/xlsx.py` writes a workbook, both fed by `reports/builder.py`. The
finished file is kept with the report record, so the app needs no media folder
to serve it.

## Where it is wired

| File | What is there |
| --- | --- |
| `smst_ai/urls.py` | `path("smst_finances/", include("smst_finances.urls"))` — the app opens on `/smst_finances/` |
| `cloud/routing.py` | the websocket route, which `asgi.py` reads |
| `router/app/urls.py` | the same mount, for when the app host points at `router.app.urls` |
| `router/app/views.py` | the old `?smst_app=smst_finances` link redirects to the start URL |
| `templates/app/homepage.html` | the SmSt Finances card opens the start URL |
| `templates/app/format/app_home.html` | `extra_head` and `extra_scripts` blocks for the app's own CSS and JS |

## Putting it live

```bash
python manage.py makemigrations smst_finances
python manage.py migrate
python manage.py collectstatic --noinput
```

Migrations are not tracked in this repository, so the first two commands have to
run wherever the app is served.
