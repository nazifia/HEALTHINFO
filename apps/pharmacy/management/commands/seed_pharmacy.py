"""Dev seed for the pharmacy module. Idempotent: re-runnable, safe to repeat.

    python manage.py seed_pharmacy              # demo tenant
    python manage.py seed_pharmacy --reset      # wipe this tenant's pharmacy
    python manage.py seed_pharmacy --tenant foo

Fills one pharmacy with enough to click through every screen: suppliers, a
priced item list with dated batches (some low, some near expiry), an open
purchase order part-delivered, cash and HMO sales, and a claim batch that has
been submitted, approved and part-paid.

Passes tenant= explicitly so it works without the request middleware bound.

ponytail: fixed catalogue, no faker, no volume flags. `--reset` is the only
knob, because the one thing a demo actually needs is a clean re-run.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.patients.models import Patient
from apps.pharmacy.models import (
    HMO, Claim, ClaimBatch, HmoEnrollment, PurchaseOrder, PurchaseOrderLine,
    Sale, SaleItem, StockBatch, StockItem, StockMovement, Supplier,
    TillSession,
    claim_for_sale, receive_purchase_line, receive_stock,
)
from apps.tenants.models import Tenant

PASSWORD = "devpass123"  # ponytail: dev-only shared password, never ships to prod

# name, form, unit price, cost, reorder level, [(batch, days to expiry, qty)]
CATALOGUE = [
    ("Paracetamol 500mg", "tablet", "12.50", "5.00", 100,
     [("PC-2401", 25, 240), ("PC-2405", 400, 600)]),
    ("Amoxicillin 500mg caps", "capsule", "85.00", "52.00", 60,
     [("AM-118", 50, 40)]),
    ("Artemether/Lumefantrine 20/120", "tablet", "1650.00", "1180.00", 30,
     [("AL-77", 200, 88)]),
    ("Metformin 500mg", "tablet", "38.00", "22.00", 80,
     [("MF-9", 18, 55), ("MF-12", 540, 300)]),
    ("ORS sachet", "consumable", "150.00", "95.00", 50, []),  # never stocked
    ("Ceftriaxone 1g injection", "injection", "2400.00", "1750.00", 20,
     [("CF-31", 40, 12)]),
    ("Salbutamol inhaler", "other", "3800.00", "2900.00", 10,
     [("SB-5", 300, 24)]),
    ("Cough syrup 100ml", "syrup", "950.00", "610.00", 25,
     [("CS-14", 55, 31)]),
]

# Deleted in FK order: PROTECT means a supplier or an item cannot go before the
# rows pointing at it.
RESET_MODELS = (Claim, ClaimBatch, SaleItem, Sale, StockMovement,
                PurchaseOrderLine, PurchaseOrder, StockBatch, StockItem,
                HmoEnrollment, HMO, Supplier)


class Command(BaseCommand):
    help = "Seed pharmacy demo data (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo", help="Tenant slug.")
        parser.add_argument("--reset", action="store_true",
                            help="Delete this tenant's pharmacy rows first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(
                f"No tenant with slug {opts['tenant']!r}. Run seed_dev first."
            )
        today = timezone.localdate()

        if opts["reset"]:
            for model in RESET_MODELS:
                deleted, _ = model.all_objects.filter(tenant=tenant).delete()
                if deleted:
                    self.stdout.write(f"deleted {deleted} {model.__name__}")

        staff = self._user(tenant, "08031110001", Role.PHARMACIST, "counter")
        self._user(tenant, "08031110002", Role.TENANT_ADMIN, "manager")

        emzor, _ = Supplier.all_objects.get_or_create(
            tenant=tenant, name="Emzor Pharmaceuticals",
            defaults={"contact_person": "Sales desk", "phone": "08030000001"})
        fidson, _ = Supplier.all_objects.get_or_create(
            tenant=tenant, name="Fidson Healthcare",
            defaults={"phone": "08030000002"})

        items = {}
        for name, form, price, cost, reorder, batches in CATALOGUE:
            item, _ = StockItem.all_objects.get_or_create(
                tenant=tenant, name=name,
                defaults={"form": form, "unit_price": Decimal(price),
                          "cost_price": Decimal(cost), "reorder_level": reorder},
            )
            items[name] = item
            for batch_number, days, qty in batches:
                if StockBatch.all_objects.filter(item=item,
                                                 batch_number=batch_number).exists():
                    continue
                receive_stock(item, qty, batch_number=batch_number,
                              expiry_date=today + timedelta(days=days),
                              cost_price=Decimal(cost),
                              supplier=emzor if days % 2 else fidson, user=staff)
        self.stdout.write(f"items: {len(items)}")

        self._purchase_order(tenant, items, fidson, staff, today)

        hygeia, _ = HMO.all_objects.get_or_create(
            tenant=tenant, name="Hygeia HMO",
            defaults={"code": "HYG", "coverage_percent": Decimal("70.00")})
        HMO.all_objects.get_or_create(
            tenant=tenant, name="NHIA",
            defaults={"code": "NHIA", "coverage_percent": Decimal("90.00")})
        # The per-sale insurer: its claims go out as they are raised, so the
        # demo has both routes on screen - one batched, one already submitted.
        reliance, _ = HMO.all_objects.get_or_create(
            tenant=tenant, name="Reliance HMO",
            defaults={"code": "REL", "coverage_percent": Decimal("80.00"),
                      "auto_submit_claims": True})

        if not Sale.all_objects.filter(tenant=tenant).exists():
            self._sales(tenant, items, hygeia, reliance, staff, today)

        self.stdout.write(self.style.SUCCESS(
            f"seed_pharmacy complete - counter login {staff.phone[-6:]} / {PASSWORD}"
        ))

    def _user(self, tenant, phone, role, username):
        """Create or re-point a demo user, always with the dev password."""
        user, _ = User.objects.get_or_create(
            phone=phone, defaults={"tenant": tenant, "role": role,
                                   "username": username})
        user.tenant, user.role, user.username = tenant, role, username
        user.set_password(PASSWORD)
        user.save()
        return user

    def _purchase_order(self, tenant, items, supplier, staff, today):
        """One order, submitted and part-delivered — the PARTIAL state on screen."""
        if PurchaseOrder.all_objects.filter(tenant=tenant).exists():
            return
        order = PurchaseOrder.all_objects.create(
            tenant=tenant, supplier=supplier, ordered_by=staff,
            expected_date=today + timedelta(days=7),
            notes="Monthly restock.")
        ors = PurchaseOrderLine.all_objects.create(
            tenant=tenant, order=order, item=items["ORS sachet"],
            quantity_ordered=200, unit_cost=Decimal("95.00"))
        PurchaseOrderLine.all_objects.create(
            tenant=tenant, order=order, item=items["Ceftriaxone 1g injection"],
            quantity_ordered=50, unit_cost=Decimal("1750.00"))
        order.submit()
        # Half the ORS arrives; the antibiotic is back-ordered.
        receive_purchase_line(ors, 80, batch_number="ORS-9",
                              expiry_date=today + timedelta(days=600),
                              user=staff)
        self.stdout.write(f"purchase order: {order.reference} ({order.status})")

    @staticmethod
    def _round_up(amount):
        """The note a patient would actually hand over for that bill."""
        return (amount / Decimal("500")).to_integral_value(rounding="ROUND_CEILING") * Decimal("500")

    def _sales(self, tenant, items, hmo, auto_hmo, staff, today):
        """Five sales — cash paid, cash part-paid, two insured on the batched
        scheme, and one on the scheme that submits per sale."""
        patient, _ = Patient.all_objects.get_or_create(
            tenant=tenant, first_name="Ada", last_name="Obi",
            defaults={"sex": "F",
                      "date_of_birth": today - timedelta(days=365 * 34)})
        member, _ = HmoEnrollment.all_objects.get_or_create(
            tenant=tenant, patient=patient, hmo=hmo,
            defaults={"member_number": "HYG-40192", "plan": "Bronze"})

        # The counter opens a drawer first, so the cash below has somewhere to
        # go and the shift can be reconciled at the end of the day.
        till, _ = TillSession.all_objects.get_or_create(
            tenant=tenant, opened_by=staff, status=TillSession.Status.OPEN,
            defaults={"opening_float": Decimal("5000.00")},
        )

        cash = Sale.all_objects.create(tenant=tenant, served_by=staff,
                                       payment_method=Sale.PaymentMethod.CASH)
        cash.add_line(items["Paracetamol 500mg"], 20, user=staff)
        cash.add_line(items["Cough syrup 100ml"], 1, user=staff)
        # Paid with a round note, so the drawer shows change going back out.
        cash.record_payment(self._round_up(cash.patient_payable), till=till,
                            user=staff)

        owing = Sale.all_objects.create(tenant=tenant, served_by=staff,
                                        payment_method=Sale.PaymentMethod.CASH)
        owing.add_line(items["Metformin 500mg"], 30, user=staff)
        # Part-paid: shows as owed.
        owing.record_payment(Decimal("500.00"), till=till, user=staff)

        for lines in ([("Artemether/Lumefantrine 20/120", 2),
                       ("Amoxicillin 500mg caps", 15)],
                      [("Ceftriaxone 1g injection", 3)]):
            sale = Sale.all_objects.create(
                tenant=tenant, patient=patient, enrollment=member,
                payment_method=Sale.PaymentMethod.HMO, served_by=staff)
            for name, qty in lines:
                sale.add_line(items[name], qty, user=staff)
            claim_for_sale(sale)
            # An insured co-payment is taken in cash, so it reaches the drawer.
            sale.record_payment(sale.patient_payable, till=till, user=staff)

        # Bola is on the auto-submitting scheme and on nothing else, so the
        # counter can sell to her without naming a card: the API finds the one
        # valid membership, and the claim leaves as SUBMITTED, not DRAFT.
        bola, _ = Patient.all_objects.get_or_create(
            tenant=tenant, first_name="Bola", last_name="Eze",
            defaults={"sex": "F",
                      "date_of_birth": today - timedelta(days=365 * 41)})
        bola_member, _ = HmoEnrollment.all_objects.get_or_create(
            tenant=tenant, patient=bola, hmo=auto_hmo,
            defaults={"member_number": "REL-88117", "plan": "Gold"})
        auto = Sale.all_objects.create(
            tenant=tenant, patient=bola, enrollment=bola_member,
            payment_method=Sale.PaymentMethod.HMO, served_by=staff)
        auto.add_line(items["Salbutamol inhaler"], 1, user=staff)
        auto.add_line(items["Paracetamol 500mg"], 10, user=staff)
        auto_claim = claim_for_sale(auto)
        auto.record_payment(auto.patient_payable, till=till, user=staff)
        self.stdout.write(
            f"auto-submitted claim {auto_claim.reference} ({auto_claim.status})")

        batch = ClaimBatch.all_objects.create(
            tenant=tenant, hmo=hmo, period_start=today - timedelta(days=30),
            period_end=today)
        batch.add_claims(list(Claim.all_objects.filter(tenant=tenant, hmo=hmo)))
        batch.submit()
        batch.approve_all()
        batch.record_payment(Decimal("1000.00"))  # part-settled
        self.stdout.write(
            f"sales: {Sale.all_objects.filter(tenant=tenant).count()}, "
            f"claim batch {batch.reference} ({batch.status})")
