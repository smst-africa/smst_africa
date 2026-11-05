"""Support content for the SmSt Apps.

The whole support centre lives in this module: one manual set, one tip set
and one release history per app. Nothing here touches the database, so the
templates stay free of hard coded help text and the content can be edited
without a migration.

shortcut: the copy is Python, upgrade to models and the admin when people who
are not developers need to publish a manual or a release note themselves.
"""

from __future__ import annotations

from django.http import Http404
from django.urls import reverse

from smst_app.views import ACCOUNT_URL, APPS as CORE_APPS, ORDER

CONTACT_EMAIL = "smartstock.africa@gmail.com"

HUB = {
    "title": "The manual, the tip, and what changed.",
    "lede": (
        "Three apps, one support desk. Each app carries its own manual, its "
        "own tips and its own release history. Pick an app and read it the "
        "way you would read the shop notebook."
    ),
    "manuals_intro": "Open a manual, follow the numbered steps, and keep the page beside you at the counter.",
    "tips_intro": "Short notes from the shops running these apps every day.",
    "updates_intro": "What changed, when it changed and what it means for the work you do.",
}

HUB_APP = {
    "slug": "support",
    "name": "SmSt Support",
    "short": "Support",
    "initial": "S",
    "kicker": "Manuals, tips and what changed",
    "open_url": "/support/",
    "page_title": "SmSt Support: manuals, tips and version updates",
    "page_description": (
        "Manuals, tips and version updates for SmSt Works, SmSt Stocks and "
        "SmSt Finances. Each app reads in its own colour."
    ),
    "theme": "#1f2937",
}

SUPPORT = {
    "works": {
        "tagline": "The floor, the ranks and the day's work.",
        "headline": "Run the floor without the guesswork.",
        "intro": (
            "Set up the shop floor, give every person the right rank, and keep "
            "the job timeline honest. This is the support desk for SmSt Works."
        ),
        "manuals_intro": "Start with the first day, then build the jobs that keep stock moving.",
        "tips_intro": "Habits that keep ranks, jobs and the timeline in good order.",
        "updates_intro": "Every change to SmSt Works, newest first.",
        "version": "1.4",
        "updated": "October 2026",
        "manuals": [
            {
                "slug": "open-the-floor",
                "title": "Open the shop floor",
                "role": "Owner",
                "minutes": 6,
                "summary": "Create the shop, add the team, and open the live timeline for the first time.",
                "steps": [
                    "Sign in to your account and open SmSt Works from the app catalogue.",
                    "Create the shop with its name, town and opening hours.",
                    "Add each employee and give them a rank before their first shift.",
                    "Set the working hours so the timeline reads against the right day.",
                    "Open the timeline and check that the floor and the team both show.",
                ],
            },
            {
                "slug": "hire_an_employee",
                "title": "How to Hire an employee",
                "role": "Owner",
                "minutes": 6,
                "summary": "Ask employee to create a smst account, use email to add to shop, set permissions and rank.",
                "steps": [
                    "Open Smst Works and Navigate to Employees.",
                    "Press Hire an employee button.",
                    "Fill in the employee's details and enter the email the employee has logged in Smst.",
                    "Set the working hours so the timeline reads against the right day.",
                    "Open the timeline and check that the floor and the team both show.",
                ],
            },
            {
                "slug": "build-a-job",
                "title": "Build a job that moves stock",
                "role": "Manager",
                "minutes": 8,
                "summary": "A job takes items in, puts items out, and writes the movement for you.",
                "steps": [
                    "Open Jobs and choose a new job.",
                    "Name the job after the work, for example Pack shelves.",
                    "Add the inputs: each item and the quantity the job consumes.",
                    "Add the outputs: each item and the quantity the job produces.",
                    "Choose the rank that may run the job and save it.",
                    "Run the job once with a small quantity and read the timeline.",
                ],
            },
            {
                "slug": "rank-a-person",
                "title": "Rank a person to the work",
                "role": "Owner",
                "minutes": 5,
                "summary": "A rank decides which pages a person sees, what they may do, and which rows they may read.",
                "steps": [
                    "Open Ranks and create a rank named after the work, not the person.",
                    "Choose the pages the rank may open.",
                    "Choose the actions the rank may take on each page.",
                    "Choose the rows the rank may see, for example their own shop only.",
                    "Assign the rank to the people who do that work.",
                    "Sign in as one of them and confirm the floor reads correctly.",
                ],
            },
            {
                "slug": "loyalty-suppliers-guides",
                "title": "Loyalty, suppliers and shared guides",
                "role": "Manager",
                "minutes": 7,
                "summary": "Keep the regulars, the people who deliver, and the notes that train a new hire.",
                "steps": [
                    "Open Loyalty and add a customer with their phone number.",
                    "Set the points rule so a sale earns what the shop promised.",
                    "Open Suppliers and add each supplier with a contact and lead time.",
                    "Open Guides and write the note a new hire needs on day one.",
                    "Share the guide with the rank that needs it.",
                ],
            },
        ],
        "tips": [
            {
                "tag": "Ranks",
                "title": "Name ranks after the work",
                "body": "A rank called Floor manager survives a change of staff. A rank called Brian does not. Name the work, then assign people to it.",
            },
            {
                "tag": "Jobs",
                "title": "Test a job with one item first",
                "body": "Run a new job with the smallest quantity that still moves stock. If the inputs and outputs land where you expect, scale it up.",
            },
            {
                "tag": "Team",
                "title": "Keep one Floor manager rank",
                "body": "Give the busy days one rank that can open every page and fix a mistake. Everyone else stays narrow, and the day keeps moving.",
            },
            {
                "tag": "Timeline",
                "title": "Read the waiting count at closing",
                "body": "Jobs still waiting at closing are the work you will pay for twice tomorrow. Clear them before you lock the shop.",
            },
        ],
        "updates": [
            {
                "version": "1.5",
                "date": "23 October 2026",
                "tag": "New",
                "title": "Fire an employee quick and easy",
                "summary": "The owner can remove employees from the workplace with a single click.",
                "changes": [
                    "A fire button option has been added to the employee record final column.",
                ],
            },
            {
                "version": "1.4",
                "date": "October 2026",
                "tag": "New",
                "title": "The live job timeline",
                "summary": "The floor now reads as job rows, with running, waiting and done states.",
                "changes": [
                    "Each job gets its own row against the working day.",
                    "Running, waiting and done are marked on the timeline.",
                    "The stat strip shows the team, jobs running, jobs waiting and loyalty points.",
                ],
            },
            {
                "version": "1.3",
                "date": "September 2026",
                "tag": "Improved",
                "title": "Ranks reach further",
                "summary": "A rank now controls pages, actions and the rows a person may read.",
                "changes": [
                    "Ranks carry separate page, action and row permissions.",
                    "A shop owner can keep a person inside one shop.",
                    "The rank editor shows what each choice reveals.",
                ],
            },
            {
                "version": "1.2",
                "date": "August 2026",
                "tag": "New",
                "title": "Loyalty customers and suppliers",
                "summary": "Regulars, points and the people who deliver now live beside the floor.",
                "changes": [
                    "Loyalty customers keep points and history.",
                    "Suppliers keep a contact and a delivery lead time.",
                    "Shared guides can be attached to a rank.",
                ],
            },
        ],
    },
    "stocks": {
        "tagline": "The shelf, the movements and what it is worth.",
        "headline": "Catalogue the shelf, then let the numbers catch up.",
        "intro": (
            "Add the products, record every movement, and read the value of "
            "the shelf without counting it by hand. This is the support desk "
            "for SmSt Stocks."
        ),
        "manuals_intro": "Start with the products, then record the movements that keep the count true.",
        "tips_intro": "Notes from shops that stopped rewriting the exercise book.",
        "updates_intro": "Every change to SmSt Stocks, newest first.",
        "version": "2.1",
        "updated": "October 2026",
        "manuals": [
            {
                "slug": "add-products",
                "title": "Add the first products",
                "role": "Owner",
                "minutes": 7,
                "summary": "A product carries its photo, weight, pack size, buying price and selling price.",
                "steps": [
                    "Open SmSt Stocks and choose Items.",
                    "Ensure you have taken a photo of the product as seen by the customer sees on the shelf.",
                    "On the Items page choose Add an item.",
                    "Enter the Product Details",
                    "Product Name - What the people call it on the shelf",
                    "Product Code - What you want to identify it by (Optional)",
                    "Category - What group of product its in.",
                    "Description - Details about the product in any language in any format.",
                    "Details - Have pairs? Add a detail about it. eg Weight:500g",
                    "Picture - What it looks like on the shelf",
                    "Price and Count - How much do you buy and sell it?",
                    "In hand - How much exists right now?",
                    "Restock at - At what amount should you restock your product?",
                    "Sold By - How you sell the by?",
                    "Enter the weight, pack size and unit you will count in.",
                    "Enter the buying price and the selling price side by side.",
                    "Set the restock level from the delivery lead time.",
                    "Save the product and repeat until the shelf is catalogued.",
                ],
            },
            {
                "slug": "record-a-sale",
                "title": "Record a sale and a delivery",
                "role": "Attendant",
                "minutes": 4,
                "summary": "Every movement changes the quantity. Record it the day it happens.",
                "steps": [
                    "Open the product and choose Record movement.",
                    "Choose stock out for a sale, or stock in for a delivery.",
                    "Enter the quantity and a short reference.",
                    "Choose the reason so the report can explain the change.",
                    "Save the movement and check the new quantity on the item.",
                ],
            },
            {
                "slug": "restock",
                "title": "Restock before the shelf is empty",
                "role": "Manager",
                "minutes": 6,
                "summary": "The restock list collects low and out of stock items with a supplier and a total.",
                "steps": [
                    "Open Restock and review the items marked low or out.",
                    "Choose the supplier and the quantity to order for each item.",
                    "Create the order and keep the reference.",
                    "When the delivery arrives, receive it against the order.",
                    "Update the buying price before the next sale.",
                ],
            },
            {
                "slug": "shelf-value",
                "title": "Read the value of the shelf",
                "role": "Owner",
                "minutes": 5,
                "summary": "The stock value, the movement history and the losses all read from the same records.",
                "steps": [
                    "Open Reports and choose Stock value.",
                    "Read the value at buying price and at selling price.",
                    "Open an item's movement history to see the month.",
                    "Open Losses and check that each reason is recorded.",
                    "Export the month for your records or your accountant.",
                ],
            },
        ],
        "tips": [
            {
                "tag": "Catalogue",
                "title": "Photograph the pack the customer sees",
                "body": "The photo is a quick check at the counter. A blurred photo means a wrong item and a wrong movement.",
            },
            {
                "tag": "Restock",
                "title": "Set the restock level to the lead time",
                "body": "If delivery takes three days and you sell four a day, a reorder level below twelve is a shelf that empties before the truck arrives.",
            },
            {
                "tag": "Counting",
                "title": "Record a loss the day it happens",
                "body": "A broken pack recorded today explains the count. A broken pack remembered next month becomes a mystery.",
            },
            {
                "tag": "Margin",
                "title": "Update the buying price on every delivery",
                "body": "The margin is only true when the buying price is current. Two minutes at delivery keeps the report honest.",
            },
        ],
        "updates": [
            {
                "version": "2.2",
                "date": "October 2026",
                "tag": "New",
                "title": 'The Cart',
                "summary": 'Hold more than one stock item in cart',
                "changes":[
                    "Choose whether to buy or sell products",
                    "Apply finance options on the items in cart",
                    "Choose a Finance Account to process the payment through.",
                    "Download Receipts to print for customers."
                ]
            },
            {
                "version": "2.1",
                "date": "October 2026",
                "tag": "New",
                "title": "The reorder list",
                "summary": "Low and out of stock items now gather in one list with a supplier and a total.",
                "changes": [
                    "Low, out and healthy items are separated.",
                    "A supplier and a quantity can be chosen per item.",
                    "The list carries a running order total.",
                ],
            },
            {
                "version": "2.0",
                "date": "September 2026",
                "tag": "Improved",
                "title": "Stock value and movement history",
                "summary": "Each item now shows what it is worth and where every unit went.",
                "changes": [
                    "Stock value reads at buying price and at selling price.",
                    "Every item keeps a dated movement history.",
                    "Losses and gains carry a reason.",
                ],
            },
            {
                "version": "1.9",
                "date": "August 2026",
                "tag": "New",
                "title": "Loss and gain reasons",
                "summary": "A movement can now explain itself, so the report does not guess.",
                "changes": [
                    "Broken, expired, counted and donated reasons are built in.",
                    "A reason can carry a short note.",
                    "The loss report groups by reason and by item.",
                ],
            },
        ],
    },
    "finances": {
        "tagline": "The money book, the statements and the plan.",
        "headline": "Keep the book balanced, then read it without a second tally.",
        "intro": (
            "Record income, expenses, tax and drawings. Read the statements, "
            "budgets and graphs from one balanced book. This is the support "
            "desk for SmSt Finances."
        ),
        "manuals_intro": "Set the book up once, then post the day's entries and let the statements follow.",
        "tips_intro": "Small money habits that keep the statements worth reading.",
        "updates_intro": "Every change to SmSt Finances, newest first.",
        "version": "1.6",
        "updated": "October 2026",
        "manuals": [
            {
                "slug": "set-up-the-book",
                "title": "Set up the money book",
                "role": "Owner",
                "minutes": 8,
                "summary": "Choose the currency, set the rules, and give the book its opening balances.",
                "steps": [
                    "Open SmSt Finances and choose the currency the shop trades in.",
                    "Set the tax rule, the discount rule and any payment fee.",
                    "Review the chart of accounts and rename what your shop calls each line.",
                    "Enter the opening balances for cash, bank, stock and any loan.",
                    "Post the opening entry and check that the book balances.",
                ],
            },
            {
                "slug": "record-income-and-expenses",
                "title": "Record income and expenses",
                "role": "Clerk",
                "minutes": 5,
                "summary": "One entry posts to two accounts, so the book stays balanced without a second tally.",
                "steps": [
                    "Open the money book and choose New entry.",
                    "Choose income or expense and the account it belongs to.",
                    "Enter the amount, the date and the payment method.",
                    "Add the tax or the discount if the entry carries one.",
                    "Write a short note so the entry explains itself later.",
                    "Post the entry and confirm the new balance.",
                ],
            },
            {
                "slug": "drawings-and-tax",
                "title": "Drawings, owners and tax",
                "role": "Owner",
                "minutes": 6,
                "summary": "Money taken out by an owner is a drawing, not an expense, and the book should say so.",
                "steps": [
                    "Open the owner account and choose Record drawing.",
                    "Enter the amount, the date and where the money went.",
                    "Keep the drawing out of the expense accounts.",
                    "Check the tax rule on the entries that carry tax.",
                    "Read the owner statement before the end of the month.",
                ],
            },
            {
                "slug": "read-statements-and-budgets",
                "title": "Read the statements and budgets",
                "role": "Owner",
                "minutes": 7,
                "summary": "Cash, profit and loss, and the balance sheet all read from the posted lines.",
                "steps": [
                    "Open Statements and choose the period you want to read.",
                    "Start with Cash to see what actually moved.",
                    "Open Profit and loss to see what the month earned.",
                    "Open the balance sheet to see what the shop owns and owes.",
                    "Open Budgets and compare the plan with the posted lines.",
                    "Export the period for your records or your accountant.",
                ],
            },
        ],
        "tips": [
            {
                "tag": "Habit",
                "title": "Post at the end of the day",
                "body": "A day of entries takes ten minutes. A month of entries takes a weekend you will not enjoy.",
            },
            {
                "tag": "Accounts",
                "title": "One account for each thing you want to see",
                "body": "If you want to know what transport costs, give transport its own account. A line called Other hides the answer.",
            },
            {
                "tag": "Tax",
                "title": "Set the tax rule before the first sale",
                "body": "The rule belongs in the setup, not in a note on a receipt. Set it once and every entry that follows carries it.",
            },
            {
                "tag": "Budgets",
                "title": "Compare the budget weekly",
                "body": "The budget is useful while there is still time to change the week. Read it before Sunday, not after.",
            },
        ],
        "updates": [
            {
                "version": "1.6",
                "date": "October 2026",
                "tag": "New",
                "title": "The weekly spend chart",
                "summary": "The budget card now shows the week as a bar chart beside the plan.",
                "changes": [
                    "Each week is drawn against its budget line.",
                    "Overspend is marked in a warning colour.",
                    "The chart reads from the posted entries only.",
                ],
            },
            {
                "version": "1.5",
                "date": "September 2026",
                "tag": "Improved",
                "title": "Budget lines from posted entries",
                "summary": "Budgets now compare the plan with the lines that were actually posted.",
                "changes": [
                    "A budget line can follow an account.",
                    "The comparison shows plan, posted and the difference.",
                    "The month can be closed without losing the history.",
                ],
            },
            {
                "version": "1.4",
                "date": "August 2026",
                "tag": "New",
                "title": "Tax, discount and fee rules",
                "summary": "Rules set once now follow an entry through to the statement.",
                "changes": [
                    "Tax rules can be set per account.",
                    "Discounts no longer change the posted total.",
                    "Payment fees post to their own line.",
                ],
            },
        ],
    },
}


def _with_numbers(manuals):
    return [
        {**manual, "number": f"{index:02d}"}
        for index, manual in enumerate(manuals, start=1)
    ]


def _app_url(slug):
    return reverse("smst_support:app", kwargs={"slug": slug})


def support_app(slug):
    """Everything the per-app support page needs, or a 404 for an unknown app."""
    if slug not in SUPPORT:
        raise Http404(f"No support content for {slug}")

    core = CORE_APPS[slug]
    data = SUPPORT[slug]
    manuals = _with_numbers(data["manuals"])

    return {
        "slug": slug,
        "name": core["name"],
        "short": core["short"],
        "initial": core["initial"],
        "kicker": core["kicker"],
        "theme": core["theme"],
        "open_url": core["open_url"],
        "page_title": f"{core['name']} support: manuals, tips and release notes",
        "page_description": data["intro"],
        "tagline": data["tagline"],
        "headline": data["headline"],
        "intro": data["intro"],
        "manuals_intro": data["manuals_intro"],
        "tips_intro": data["tips_intro"],
        "updates_intro": data["updates_intro"],
        "version": data["version"],
        "updated": data["updated"],
        "manuals": manuals,
        "tips": data["tips"],
        "updates": data["updates"],
        "manual_count": len(manuals),
        "tip_count": len(data["tips"]),
        "update_count": len(data["updates"]),
    }


def support_apps():
    """The three app cards used on the hub and in the support switcher."""
    return [
        {
            "slug": slug,
            "name": CORE_APPS[slug]["name"],
            "short": CORE_APPS[slug]["short"],
            "initial": CORE_APPS[slug]["initial"],
            "theme": CORE_APPS[slug]["theme"],
            "open_url": CORE_APPS[slug]["open_url"],
            "tagline": SUPPORT[slug]["tagline"],
            "version": SUPPORT[slug]["version"],
            "updated": SUPPORT[slug]["updated"],
            "manual_count": len(SUPPORT[slug]["manuals"]),
            "tip_count": len(SUPPORT[slug]["tips"]),
            "update_count": len(SUPPORT[slug]["updates"]),
            "url": _app_url(slug),
        }
        for slug in ORDER
    ]


def nav_apps():
    """The app tabs for the shared landing header. None of them is current."""
    return [
        {
            "slug": slug,
            "name": CORE_APPS[slug]["name"],
            "short": CORE_APPS[slug]["short"],
            "kicker": CORE_APPS[slug]["kicker"],
            "url": reverse(slug),
            "current": False,
        }
        for slug in ORDER
    ]


def hub_summary():
    """Totals, latest changes and popular tips for the support hub."""
    apps = support_apps()
    latest = []
    tips = []

    for slug in ORDER:
        core = CORE_APPS[slug]
        update = SUPPORT[slug]["updates"][0]
        latest.append(
            {
                "app": core["name"],
                "short": core["short"],
                "theme": core["theme"],
                "version": update["version"],
                "date": update["date"],
                "title": update["title"],
                "body": update["summary"],
                "url": f"{_app_url(slug)}#updates",
            }
        )
        for tip in SUPPORT[slug]["tips"][:2]:
            tips.append(
                {
                    "app": core["name"],
                    "short": core["short"],
                    "theme": core["theme"],
                    "url": f"{_app_url(slug)}#tips",
                    **tip,
                }
            )

    return {
        "apps": apps,
        "latest": latest,
        "tips": tips,
        "totals": {
            "apps": len(apps),
            "manuals": sum(app["manual_count"] for app in apps),
            "tips": sum(app["tip_count"] for app in apps),
            "updates": sum(app["update_count"] for app in apps),
        },
    }


def hub():
    """The hub context: app cards, latest changes, popular tips and totals."""
    return {**HUB, **hub_summary()}
