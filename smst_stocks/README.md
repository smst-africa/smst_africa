# SmSt Stocks

The first SmSt App: a stock book for a shop. It holds what the shop sells, what
each item cost, what it sells for, how many are in hand, and a ledger of every
movement that made the number what it is.

The app opens on `/smst_stocks/` on the app host.

```
https://app.smartstock.africa/smst_stocks/
```

## What it does

- **Shops.** An account can run more than one. The free plan carries one shop
  and 50 items, SmSt Pro carries unlimited shops and 2,000 items a shop.
- **Items.** A product, its buying price, its selling price, how many are in
  hand, the level at which it needs ordering, and any details worth showing
  (`Weight: 500g`). Photos go to Cloudinary.
- **The ledger.** Every change to a quantity is written as a movement: a sale, a
  delivery, a return, a loss or an adjustment. The count on the screen is the
  sum of the ledger, so the two can never disagree.
- **The money side.** A movement form also asks where the money moved, listing
  the shop's chart of accounts (Cash, Bank, Receivables, Inventory). A sale
  posts money in, a delivery posts money out, a return posts a refund, and a
  loss writes its cost off stock. SmSt Finances is updated in the same request
  and tells its open dashboard over the websocket.
- **Reordering.** Items at or below their reorder level are listed with the
  quantity to ask the supplier for and what it will cost.
- **Shared pages.** Publish an item and share its link. The page shows what is
  in hand right now and lets a customer ask for it. The shop is told
  immediately, and the stock is held so it cannot be promised twice.
- **Reports.** Stock valuation, the movements, the reorder list and the orders,
  as a PDF for a supplier or a spreadsheet for the shop's own records.
- **Live updates.** A websocket keeps the dashboard, and any open shared page,
  up to date as stock moves.

## The API

Everything the app does goes through the API, under `/smst_stocks/api/`.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `shops/` | The shops of the signed in user |
| `POST` | `shops/` | Create a shop |
| `PATCH` | `shops/<id>/` | Change the shop |
| `GET` | `shops/<id>/summary/` | The totals: value, units, low stock, orders |
| `GET` `POST` | `products/` | List and create items |
| `PATCH` `DELETE` | `products/<id>/` | Change and remove an item |
| `POST` | `products/<id>/movement/` | Record a movement against an item |
| `POST` | `products/<id>/publish/` | Show the item on its shared page, or hide it |
| `POST` | `products/<id>/share/` | Create a link to the shared page |
| `GET` | `products/low_stock/` | The items that need ordering |
| `POST` | `products/delivery/` | Record a delivery of several lines |
| `GET` `POST` | `movements/` | The ledger |
| `GET` `POST` | `orders/` | The orders of the shop |
| `POST` | `orders/<id>/cancel/` | Cancel an order and put the stock back |
| `GET` `POST` | `links/` | The shared links |
| `GET` `POST` | `reports/` | The reports, and a request for a new one |
| `GET` | `reports/<id>/download/` | The file a report produced |

The open endpoints, for customers who have a shared link and no account:

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `public/products/<token>/` | The item, its price and what is in hand |
| `GET` | `public/shops/<token>/` | The catalogue a shop shares |
| `GET` | `public/catalogue/` | Every published item |
| `POST` | `public/orders/` | Ask for an item |

A movement is written with the number the shopkeeper typed. The kind decides
the direction: a sale of 3 takes 3 off the shelf, a delivery of 20 puts 20 on
it, and an adjustment keeps the sign it was given.

## The websocket

```
ws://<host>/ws/smst_stocks/shop/          the dashboard of the signed in user
ws://<host>/ws/smst_stocks/product/<id>/  a shared product page
```

Messages look like this:

```json
{"event": "product.moved", "data": {"id": 14, "name": "Mumias Sugar 1kg", "quantity": 21.0, "state": "in_stock", "summary": {}}}
```

`order.created`, `order.updated` and `report.ready` are sent the same way.

## Background work

| Task | What it does |
| --- | --- |
| `smst_stocks.tasks.generate_report` | Builds a report and tells the shop it is ready |
| `smst_stocks.tasks.notify_new_order` | Tells the owner that a customer asked for stock |
| `smst_stocks.tasks.low_stock_digest` | A morning list of what is running low |

The digest is meant to run once a day. Add it to the celery beat schedule in
your settings:

```python
CELERY_BEAT_SCHEDULE = {
    "smst-stocks-low-stock-digest": {
        "task": "smst_stocks.tasks.low_stock_digest",
        "schedule": 60.0 * 60 * 7,
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
| `smst_ai/urls.py` | `path("smst_stocks/", include("smst_stocks.urls"))` — the app opens on `/smst_stocks/` |
| `cloud/routing.py` | the websocket routes, which `asgi.py` reads |
| `router/app/urls.py` | the same mount, for when the app host points at `router.app.urls` |
| `router/app/views.py` | the old `?smst_app=smst_stocks` link redirects to the start URL |
| `templates/app/homepage.html` | the SmSt Stocks card opens the start URL |
| `templates/app/format/app_home.html` | `extra_head` and `extra_scripts` blocks for the app's own CSS and JS |

## Putting it live

```bash
python manage.py makemigrations smst_stocks
python manage.py migrate
python manage.py collectstatic --noinput
```

Migrations are not tracked in this repository, so the first two commands have to
run wherever the app is served.
