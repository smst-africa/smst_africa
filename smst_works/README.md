# SmSt Works

The people app of SmSt: the shop floor behind the counter. It holds the team and
what each rank may do, the loyalty customers, the suppliers, the guides anyone
can read, and the jobs that turn stock inputs into stock outputs while the clock
runs.

The app opens on `/smst_works/` on the app host.

```
https://app.smartstock.africa/smst_works/
```

## What it does

- **The team and their ranks.** An employee is a person in a shop with a rank.
  A rank is a list of permission keys, so the shop decides what a manager, an
  accountant, a cleaner or any other title may do. The owner always has every
  permission. Hiring links an existing login by email; a person with no rank has
  no permissions.
- **Loyalty customers.** Every customer carries points and a tier (`bronze`,
  `silver`, `gold`, `platinum`). Points are added or redeemed with a reason, and
  each change is kept as a loyalty transaction, so the balance always has its
  history. A redemption can never take the balance below zero.
- **Suppliers.** The people the shop buys from, with contacts, address, notes
  and the products they supply, ready when the shopkeeper needs to call.
- **Guides.** Short written instructions for opening, closing, cleaning or any
  other routine. Anyone in the shop can read a published guide; only a rank with
  `guides.manage` can write one.
- **Jobs.** A job is work with a start, a finish and a result. It lists the stock
  it takes in and the stock it turns out — 1 kg of flour, 200 g of sugar and 4
  eggs make 20 chapatis, for example. A job moves through `pending`, `running`,
  then `succeeded` or `failed`.
- **Stock on success only.** When a job succeeds, its inputs leave the shelf and
  its outputs arrive, each as an adjustment in SmSt Stocks, in one transaction.
  A failed job, or an input that is short, leaves the stock exactly as it was.
- **The live timeline.** The dashboard draws every open and recent job on a
  horizontal clock. A running job keeps growing as time passes, and a websocket
  pushes each change, so the floor sees the same picture without refreshing.
- **Live updates.** The shop websocket carries job, team, loyalty, supplier,
  guide and stock events.

## Ranks and permissions

| Key | What it allows |
| --- | --- |
| `stocks.view` | See stock |
| `stocks.add` | Add stock (deliveries) |
| `stocks.move` | Move stock (sales, losses, adjustments) |
| `customers.manage` | Manage loyalty customers |
| `suppliers.manage` | Manage suppliers |
| `jobs.create` | Create jobs |
| `jobs.run` | Start and finish jobs |
| `guides.manage` | Write guides |
| `employees.manage` | Hire and edit employees |
| `ranks.manage` | Set ranks and permissions |

Every new shop starts with three ranks: **Manager** (everything), **Accountant**
(sees stock, keeps customers, suppliers and jobs, but cannot add or move stock)
and **Cleaner** (sees and moves stock, runs jobs, but cannot add stock). The
owner can rename them, change their permissions, or add new ones.

## The API

Everything the app does goes through the API, under `/smst_works/api/`.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` `POST` | `ranks/` | The ranks and their permissions, and a new one |
| `PATCH` `DELETE` | `ranks/<id>/` | Change or remove a rank |
| `GET` `POST` | `employees/` | The team, and a new hire |
| `PATCH` `DELETE` | `employees/<id>/` | Change or remove an employee |
| `GET` `POST` | `customers/` | Loyalty customers, and a new one |
| `PATCH` `DELETE` | `customers/<id>/` | Change or remove a customer |
| `POST` | `customers/<id>/points/` | Add or redeem points |
| `GET` `POST` | `suppliers/` | Suppliers, and a new one |
| `PATCH` `DELETE` | `suppliers/<id>/` | Change or remove a supplier |
| `GET` `POST` | `guides/` | Guides, and a new one |
| `PATCH` `DELETE` | `guides/<id>/` | Change or remove a guide |
| `GET` `POST` | `jobs/` | Jobs, and a new one |
| `PATCH` `DELETE` | `jobs/<id>/` | Change or remove a job |
| `POST` | `jobs/<id>/start/` | Start a pending job |
| `POST` | `jobs/<id>/finish/` | Finish a job as succeeded or failed |
| `GET` | `timeline/` | Open and recent jobs for the timeline |
| `GET` | `summary/` | The dashboard totals for the shop |
| `POST` | `shop/movement/` | Move stock, checked against the rank |

Writes carry the shop. The view asks whether the person has the permission, and
the service asks again before it changes stock.

## The websocket

```
ws://<host>/ws/smst_works/shop/     every shop the signed in person can see
```

Messages look like this:

```json
{"event": "works.job.succeeded", "data": {"id": 14, "title": "Make chapatis", "status": "succeeded", "started_at": "2026-10-22T07:10:00Z", "finished_at": "2026-10-22T07:42:00Z"}}
```

`works.job.created`, `works.job.started`, `works.job.updated`, `works.job.failed`,
`works.stock.moved`, `works.customer.points`, `works.employee.created`,
`works.rank.updated`, `works.guide.updated` and the other create/update/delete
events are sent the same way.

## Background work

| Task | What it does |
| --- | --- |
| `smst_works.tasks.works_daily_digest` | A short workforce digest for every shop |

The digest is meant to run on a schedule. Add it to the celery beat schedule in
your settings:

```python
CELERY_BEAT_SCHEDULE = {
    "smst-works-daily-digest": {
        "task": "smst_works.tasks.works_daily_digest",
        "schedule": 60.0 * 60 * 8,
    },
}
```

## Where it is wired

| File | What is there |
| --- | --- |
| `smst_ai/urls.py` | `path("smst_works/", include("smst_works.urls"))` — the app opens on `/smst_works/` |
| `cloud/routing.py` | the websocket route, which `asgi.py` reads |
| `router/app/urls.py` | the same mount, for when the app host points at `router.app.urls` |
| `router/app/views.py` | the old `?smst_app=smst_works` link redirects to the start URL |
| `templates/app/homepage.html` | the SmSt Works card opens the start URL |
| `templates/app/format/app_home.html` | `extra_head` and `extra_scripts` blocks for the app's own CSS and JS |

## Putting it live

```bash
python manage.py makemigrations smst_works
python manage.py migrate
python manage.py collectstatic --noinput
```

Migrations are not tracked in this repository, so the first two commands have to
run wherever the app is served. The tests run with:

```bash
python manage.py test smst_works --settings=smst.test_settings
```
