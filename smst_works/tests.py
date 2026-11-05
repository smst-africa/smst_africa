"""Tests for SmSt Works.

The app runs the people side of one small shop: ranks, hiring, loyalty points,
suppliers, guides and the jobs that move stock from their inputs to their
outputs. The tests follow that shop from an empty floor to a finished job.
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
    get_user_model,
)
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from smst_stocks.models import Product, Shop, StockMovement

from .models import (
    ALL_PERMISSIONS,
    DEFAULT_RANKS,
    Customer,
    Employee,
    Guide,
    Job,
    LoyaltyTransaction,
    Rank,
    Supplier,
)
from .services import (
    WorksError,
    adjust_points,
    create_job,
    ensure_default_ranks,
    finish_job,
    hire_employee,
    permissions_for,
    record_shop_movement,
    shops_for,
    start_job,
    timeline_jobs,
)

User = get_user_model()


@override_settings(ROOT_URLCONF="smst_ai.urls")
class WorksTestCase(TestCase):
    """A shop with flour, sugar, chapati and the people who work there."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="njeri", email="njeri@example.test", password="s3cret-pass-123"
        )
        self.client = self.client_class(
            SERVER_NAME="app.smartstock.africa",
            HTTP_HOST="app.smartstock.africa",
        )
        self.sign_in(self.user)

        self.shop = Shop.objects.create(owner=self.user, name="Sokoni Traders")
        self.flour = Product.objects.create(
            shop=self.shop,
            name="Wheat Flour",
            buying_price=Decimal("120"),
            selling_price=Decimal("150"),
            quantity=Decimal("10"),
            unit="kg",
        )
        self.sugar = Product.objects.create(
            shop=self.shop,
            name="Sugar",
            buying_price=Decimal("140"),
            selling_price=Decimal("170"),
            quantity=Decimal("5"),
            unit="kg",
        )
        self.chapati = Product.objects.create(
            shop=self.shop,
            name="Chapati",
            buying_price=Decimal("0"),
            selling_price=Decimal("20"),
            quantity=Decimal("0"),
            unit="piece",
        )
        self.ranks = ensure_default_ranks(self.shop)

        self.worker = User.objects.create_user(
            username="amina", email="amina@example.test", password="s3cret-pass-123"
        )
        self.cleaner = Employee.objects.create(
            shop=self.shop,
            user=self.worker,
            name="Amina",
            rank=self.ranks["Cleaner"],
        )

    def sign_in(self, user):
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = (
            "allauth.account.auth_backends.AuthenticationBackend"
        )
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def api(self, method, path, payload=None):
        return getattr(self.client, method)(
            "/smst_works/api/" + path,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    # --------------------------------------------------------------- ranks
    def test_default_ranks_are_seeded_once(self):
        self.assertEqual(
            Rank.objects.filter(shop=self.shop).count(), len(DEFAULT_RANKS)
        )
        ensure_default_ranks(self.shop)
        self.assertEqual(
            Rank.objects.filter(shop=self.shop).count(), len(DEFAULT_RANKS)
        )

    def test_accountant_and_cleaner_get_the_right_permissions(self):
        accountant = self.ranks["Accountant"]
        cleaner = self.ranks["Cleaner"]
        self.assertTrue(accountant.has("stocks.view"))
        self.assertFalse(accountant.has("stocks.add"))
        self.assertFalse(accountant.has("stocks.move"))
        self.assertTrue(accountant.has("stocks.ledger.all"))
        self.assertTrue(accountant.has("finances.graphs.generate"))
        self.assertTrue(cleaner.has("stocks.move"))
        self.assertFalse(cleaner.has("stocks.add"))
        self.assertTrue(cleaner.has("stocks.view.movements"))
        self.assertFalse(cleaner.has("stocks.ledger.all"))
        self.assertTrue(cleaner.has("finances.view.entries"))
        self.assertFalse(cleaner.has("finances.entries.all"))

    def test_owner_has_every_permission(self):
        self.assertEqual(
            permissions_for(self.shop, self.user), frozenset(ALL_PERMISSIONS)
        )

    # ------------------------------------------------------------- people
    def test_employee_belongs_to_the_shop_they_work_at(self):
        self.assertIn(self.shop, shops_for(self.worker))

    def test_an_employee_without_a_rank_has_no_permissions(self):
        rankless = User.objects.create_user(
            username="peter", email="peter@example.test", password="x"
        )
        Employee.objects.create(shop=self.shop, user=rankless, name="Peter")
        self.assertEqual(permissions_for(self.shop, rankless), frozenset())

    def test_hiring_links_an_existing_login_by_email(self):
        person = User.objects.create_user(
            username="peter", email="peter@example.test", password="x"
        )
        employee = hire_employee(
            self.shop,
            {
                "name": "Peter",
                "email": "peter@example.test",
                "rank": self.ranks["Manager"],
            },
            self.user,
        )
        self.assertEqual(employee.user_id, person.id)
        with self.assertRaises(WorksError):
            hire_employee(
                self.shop,
                {"name": "Peter again", "email": "peter@example.test"},
                self.user,
            )

    # ------------------------------------------------------------ loyalty
    def test_points_are_added_redeemed_and_kept_in_history(self):
        customer = Customer.objects.create(shop=self.shop, name="Wanjiku")
        adjust_points(customer, 250, "First visit", self.user)
        customer.refresh_from_db()
        self.assertEqual(customer.points, 250)
        self.assertEqual(customer.tier, "silver")

        adjust_points(customer, -100, "Redeemed", self.user)
        customer.refresh_from_db()
        self.assertEqual(customer.points, 150)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(customer=customer).count(), 2
        )

    def test_points_cannot_go_below_zero(self):
        customer = Customer.objects.create(shop=self.shop, name="Wanjiku", points=30)
        with self.assertRaises(WorksError):
            adjust_points(customer, -31, "", self.user)
        customer.refresh_from_db()
        self.assertEqual(customer.points, 30)

    # --------------------------------------------------------------- jobs
    def test_successful_job_takes_inputs_and_adds_outputs(self):
        job = create_job(
            self.shop,
            {
                "title": "Make chapatis",
                "inputs": [
                    {"product": self.flour, "quantity": "1"},
                    {"product": self.sugar, "quantity": "0.2"},
                ],
                "outputs": [{"product": self.chapati, "quantity": "20"}],
            },
            self.user,
        )
        self.assertEqual(job.status, Job.PENDING)
        start_job(job, self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.RUNNING)

        finish_job(job, self.user, success=True)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.SUCCEEDED)
        self.assertIsNotNone(job.finished_at)

        self.flour.refresh_from_db()
        self.sugar.refresh_from_db()
        self.chapati.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("9"))
        self.assertEqual(self.sugar.quantity, Decimal("4.8"))
        self.assertEqual(self.chapati.quantity, Decimal("20"))
        self.assertEqual(
            StockMovement.objects.filter(
                note__contains="Make chapatis"
            ).count(),
            3,
        )

    def test_failed_job_leaves_stock_alone(self):
        job = create_job(
            self.shop,
            {
                "title": "Bake bread",
                "inputs": [{"product": self.flour, "quantity": "2"}],
            },
            self.user,
        )
        start_job(job, self.user)
        finish_job(job, self.user, success=False, note="The oven died.")
        job.refresh_from_db()
        self.assertEqual(job.status, Job.FAILED)
        self.assertEqual(job.note, "The oven died.")
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("10"))
        self.assertFalse(
            StockMovement.objects.filter(note__contains="Bake bread").exists()
        )

    def test_a_job_cannot_be_finished_twice(self):
        job = create_job(self.shop, {"title": "Clean the floor"}, self.user)
        finish_job(job, self.user)
        with self.assertRaises(WorksError):
            finish_job(job, self.user)

    def test_a_short_input_stops_the_job_and_rolls_back(self):
        job = create_job(
            self.shop,
            {
                "title": "Too much bread",
                "inputs": [{"product": self.flour, "quantity": "99"}],
                "outputs": [{"product": self.chapati, "quantity": "1"}],
            },
            self.user,
        )
        start_job(job, self.user)
        with self.assertRaises(WorksError):
            finish_job(job, self.user, success=True)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.RUNNING)
        self.flour.refresh_from_db()
        self.chapati.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("10"))
        self.assertEqual(self.chapati.quantity, Decimal("0"))

    def test_timeline_keeps_open_and_recent_jobs(self):
        open_job = create_job(self.shop, {"title": "Still running"}, self.user)
        start_job(open_job, self.user)

        done_job = create_job(self.shop, {"title": "Just finished"}, self.user)
        finish_job(done_job, self.user)

        old_job = Job.objects.create(
            shop=self.shop,
            title="Old work",
            status=Job.SUCCEEDED,
            started_at=timezone.now() - timedelta(days=4),
            finished_at=timezone.now() - timedelta(days=3),
        )
        Job.objects.filter(pk=old_job.pk).update(
            created_at=timezone.now() - timedelta(days=4)
        )

        jobs = list(timeline_jobs(self.shop, hours=24))
        self.assertIn(open_job, jobs)
        self.assertIn(done_job, jobs)
        self.assertNotIn(old_job, jobs)

    # ------------------------------------------------------- stock actions
    def test_cleaner_can_move_stock_but_cannot_add_it(self):
        with self.assertRaises(WorksError):
            record_shop_movement(
                self.shop,
                self.worker,
                self.flour,
                StockMovement.DELIVERY,
                Decimal("5"),
            )
        record_shop_movement(
            self.shop, self.worker, self.flour, StockMovement.SALE, Decimal("2")
        )
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("8"))

    def test_accountant_cannot_move_stock(self):
        accountant = User.objects.create_user(
            username="ken", email="ken@example.test", password="x"
        )
        Employee.objects.create(
            shop=self.shop,
            user=accountant,
            name="Ken",
            rank=self.ranks["Accountant"],
        )
        with self.assertRaises(WorksError):
            record_shop_movement(
                self.shop,
                accountant,
                self.flour,
                StockMovement.SALE,
                Decimal("1"),
            )
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("10"))

    # ----------------------------------------------------------------- api
    def test_the_owner_can_run_the_whole_job_through_the_api(self):
        response = self.api(
            "post",
            "jobs/",
            {
                "shop": self.shop.id,
                "title": "Make chapatis",
                "inputs": [{"product": self.flour.id, "quantity": "1"}],
                "outputs": [{"product": self.chapati.id, "quantity": "20"}],
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        job_id = response.json()["id"]

        response = self.api("post", f"jobs/{job_id}/start/", {"shop": self.shop.id})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], Job.RUNNING)

        response = self.api(
            "post", f"jobs/{job_id}/finish/", {"shop": self.shop.id, "success": True}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], Job.SUCCEEDED)
        self.flour.refresh_from_db()
        self.chapati.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("9"))
        self.assertEqual(self.chapati.quantity, Decimal("20"))

    def test_a_rank_without_jobs_create_cannot_create_a_job(self):
        watcher = User.objects.create_user(
            username="watcher", email="watcher@example.test", password="x"
        )
        rank = Rank.objects.create(
            shop=self.shop, name="Watcher", permissions=["stocks.view"]
        )
        Employee.objects.create(
            shop=self.shop, user=watcher, name="Watcher", rank=rank
        )
        self.sign_in(watcher)
        response = self.api(
            "post", "jobs/", {"shop": self.shop.id, "title": "A job"}
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_the_stock_action_api_checks_the_rank(self):
        response = self.api(
            "post",
            "shop/movement/",
            {
                "shop": self.shop.id,
                "product": self.flour.id,
                "kind": StockMovement.DELIVERY,
                "quantity": "5",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.flour.refresh_from_db()
        self.assertEqual(self.flour.quantity, Decimal("15"))

        self.sign_in(self.worker)
        response = self.api(
            "post",
            "shop/movement/",
            {
                "shop": self.shop.id,
                "product": self.flour.id,
                "kind": StockMovement.DELIVERY,
                "quantity": "5",
            },
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_customer_points_api_keeps_the_history(self):
        customer = Customer.objects.create(shop=self.shop, name="Wanjiku")
        response = self.api(
            "post",
            f"customers/{customer.id}/points/",
            {"shop": self.shop.id, "points": 120, "reason": "A good visit"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        customer.refresh_from_db()
        self.assertEqual(customer.points, 120)
        self.assertEqual(customer.loyalty_transactions.count(), 1)

    def test_supplier_api_links_items_from_the_shop(self):
        response = self.api(
            "post",
            "suppliers/",
            {
                "shop": self.shop.id,
                "name": "Nairobi Flour Millers",
                "contact_name": "Peter",
                "products": [self.flour.id, self.sugar.id],
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        supplier = Supplier.objects.get(pk=response.json()["id"])
        self.assertEqual(supplier.products.count(), 2)

    def test_guides_are_saved_and_read_back(self):
        response = self.api(
            "post",
            "guides/",
            {
                "shop": self.shop.id,
                "title": "Opening the shop",
                "category": "Opening",
                "body": "Unlock the door. Count the till.",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        guide = Guide.objects.get(pk=response.json()["id"])
        self.assertEqual(guide.title, "Opening the shop")
        self.assertEqual(guide.updated_by_id, self.user.id)

        response = self.client.get(
            "/smst_works/api/guides/", {"shop": self.shop.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"][0]["title"], "Opening the shop"
        )

    # --------------------------------------------------------------- pages
    def test_the_pages_open_for_the_owner(self):
        for name in (
            "dashboard",
            "jobs",
            "employees",
            "ranks",
            "customers",
            "suppliers",
            "guides",
        ):
            response = self.client.get(reverse("smst_works:" + name))
            self.assertEqual(response.status_code, 200, name)

    def test_a_person_without_a_shop_sees_the_empty_page(self):
        outsider = User.objects.create_user(
            username="outsider", email="outsider@example.test", password="x"
        )
        self.sign_in(outsider)
        response = self.client.get(reverse("smst_works:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The floor needs a shop")

    def test_an_employee_can_open_the_shop_floor(self):
        self.sign_in(self.worker)
        response = self.client.get(reverse("smst_works:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The work, as it happens")

    def test_a_cleaner_only_opens_the_pages_their_rank_allows(self):
        self.sign_in(self.worker)
        for name in ("dashboard", "jobs", "guides"):
            response = self.client.get(reverse("smst_works:" + name))
            self.assertEqual(response.status_code, 200, name)
        for name in ("employees", "ranks", "customers", "suppliers"):
            response = self.client.get(reverse("smst_works:" + name))
            self.assertEqual(response.status_code, 403, name)

        response = self.client.get(reverse("smst_works:dashboard"))
        self.assertNotContains(response, reverse("smst_works:ranks"))
        self.assertNotContains(response, reverse("smst_works:employees"))

        response = self.client.get(
            "/smst_works/api/ranks/", {"shop": self.shop.id}
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.get(
            "/smst_works/api/jobs/", {"shop": self.shop.id}
        )
        self.assertEqual(response.status_code, 200)
