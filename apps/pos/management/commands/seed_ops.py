"""Dev seed for everything seed_dev + seed_pharmacy leave empty. Idempotent.

    python manage.py seed_ops                 # demo tenant
    python manage.py seed_ops --tenant foo

Fills the operational side of a pharmacy so every screen has rows: staff
roster, customers with wallets and debt, a stocktake, a retail-to-wholesale
transfer, an HMO price list and a pre-authorisation, cashiers and a payment
request, a return, expenses, notifications, prescribers with a script that
raised commission and a consultation payout, and commission terms.

Run after seed_dev and seed_pharmacy: it draws items, users and HMOs from them.

ponytail: one flat handle(), each block guarded on existence. No faker, no
volume flags — a demo needs one of each state, not a thousand.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LICENSED_ROLES, Role, User
from apps.branches.models import Shift, ensure_pharmacy
from apps.customers.models import Customer
from apps.inventory.models import (
    StockCheck, StockCheckItem, StockItem, Store, TransferRequest,
    receive_stock,
)
from apps.patients.models import Patient
from apps.pharmacy.models import (
    HMO, HmoEnrollment, HmoItemRule, PreAuthorization, PreAuthorizationItem,
)
from apps.pos.models import (
    Cashier, Expense, ExpenseCategory, Notification, PaymentRequest,
    PaymentRequestItem, Sale, SaleItem, TillSession, record_return,
)
from apps.prescriptions.models import (
    Hospital, Prescriber, Prescription, PrescriptionItem,
)
from apps.reports.models import CommissionConfig
from apps.tenants.models import Jurisdiction, Tenant

PASSWORD = "devpass123"  # ponytail: dev-only shared password, never ships to prod


class Command(BaseCommand):
    help = "Seed operational demo data: roster, customers, stocktake, POS, prescribers."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo", help="Tenant slug.")

    @transaction.atomic
    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(f"No tenant {opts['tenant']!r}. Run seed_dev first.")
        items = {i.name: i for i in StockItem.all_objects.filter(tenant=tenant)}
        if "Paracetamol 500mg" not in items:
            raise CommandError("No pharmacy catalogue. Run seed_pharmacy first.")
        pharmacist = User.objects.get(tenant=tenant, username="counter")
        manager = User.objects.get(tenant=tenant, username="manager")
        nurse = User.objects.filter(tenant=tenant, role=Role.NURSE).first() or pharmacist
        branch = ensure_pharmacy(tenant)
        now = timezone.now()
        today = timezone.localdate()

        def log(label, qs):
            self.stdout.write(f"{label}: {qs.filter(tenant=tenant).count()}")

        def open_till():
            return TillSession.all_objects.filter(
                tenant=tenant, status=TillSession.Status.OPEN).first()

        # --- roster: a week of shifts, today's covers now ------------------
        if not Shift.all_objects.filter(tenant=tenant).exists():
            start = now.replace(hour=8, minute=0, second=0, microsecond=0)
            for d in range(-3, 4):
                day = start + timedelta(days=d)
                for who, h0, h1 in ((pharmacist, 0, 8), (nurse, 8, 14), (manager, 0, 10)):
                    Shift.all_objects.create(
                        tenant=tenant, user=who, branch=branch,
                        starts_at=day + timedelta(hours=h0),
                        ends_at=day + timedelta(hours=h1),
                    )
            # Make sure someone is on duty right now, whatever the clock says.
            Shift.all_objects.create(
                tenant=tenant, user=pharmacist, branch=branch,
                starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=7),
                notes="Cover",
            )
        log("shifts", Shift.all_objects)

        # --- customers: cash, wallet-funded, in debt, wholesale --------------
        if not Customer.all_objects.filter(tenant=tenant).exists():
            ada = Patient.all_objects.filter(tenant=tenant, first_name="Ada",
                                             last_name="Obi").first()
            walk = Customer.all_objects.create(
                tenant=tenant, name="Chidi Okafor", phone="08041110001",
                patient=ada, blood_group="O+", allergies=["penicillin"],
                chronic_conditions=["hypertension"],
                current_medications=["Lisinopril 10mg"],
            )
            funded = Customer.all_objects.create(
                tenant=tenant, name="Ngozi Eze", phone="08041110002",
                email="ngozi@example.com", address="12 Allen Ave, Ikeja",
            )
            funded.top_up(Decimal("20000"), method="transfer", note="Opening deposit")
            debtor = Customer.all_objects.create(
                tenant=tenant, name="Musa Bello", phone="08041110003",
            )
            debtor.top_up(Decimal("1000"))
            debtor.charge(Decimal("4500"), note="Malaria course on account")  # 3500 debt
            Customer.all_objects.create(
                tenant=tenant, name="Kano Chemists Ltd", phone="08041110004",
                is_wholesale=True, address="Sabon Gari market, Kano",
            )
            # A wallet sale, so the wallet method shows on the sales report.
            sale = Sale.all_objects.create(
                tenant=tenant, customer=funded, served_by=pharmacist,
                payment_method=Sale.PaymentMethod.WALLET, branch=branch)
            sale.add_line(items["Paracetamol 500mg"], 10, user=pharmacist)
            sale.add_line(items["Metformin 500mg"], 30, user=pharmacist)
            sale.pay_from_wallet(user=pharmacist)
            # ... and a return against it: 5 tablets back, money to the wallet.
            line = SaleItem.all_objects.filter(
                sale=sale, item=items["Paracetamol 500mg"]).first()
            record_return(line, 5, reason="Wrong strength", user=pharmacist)
            # A cash sale part-paid: shows as owed.
            owed = Sale.all_objects.create(
                tenant=tenant, customer=walk, served_by=pharmacist,
                payment_method=Sale.PaymentMethod.CASH, branch=branch)
            owed.add_line(items["Cough syrup 100ml"], 2, user=pharmacist)
            owed.record_payment(Decimal("500"), till=open_till(), user=pharmacist)
        log("customers", Customer.all_objects)

        # --- wholesale twin + transfer between stores ------------------------
        whole, made = StockItem.all_objects.get_or_create(
            tenant=tenant, name="Paracetamol 500mg (pack of 100)",
            defaults={"store": Store.WHOLESALE, "form": "tablet", "unit": "pack",
                      "unit_price": Decimal("1000.00"),
                      "cost_price": Decimal("480.00"), "reorder_level": 5},
        )
        if made:
            receive_stock(whole, 40, batch_number="PCW-1",
                          expiry_date=today + timedelta(days=500),
                          cost_price=Decimal("480.00"), user=pharmacist)
        if not TransferRequest.all_objects.filter(tenant=tenant).exists():
            retail = items["Paracetamol 500mg"]
            done = TransferRequest.all_objects.create(
                tenant=tenant, from_item=whole, to_item=retail,
                requested_quantity=5, requested_by=pharmacist,
                notes="Retail shelf running low.")
            done.approve(3, user=manager)
            done.receive()
            TransferRequest.all_objects.create(
                tenant=tenant, from_item=retail, to_item=whole,
                requested_quantity=2, requested_by=pharmacist,
            ).reject(user=manager, reason="Retail cannot spare it.")
            TransferRequest.all_objects.create(
                tenant=tenant, from_item=whole, to_item=retail,
                requested_quantity=4, requested_by=nurse)
        log("transfers", TransferRequest.all_objects)

        # --- stocktake: one completed with a write-off, one in progress ------
        if not StockCheck.all_objects.filter(tenant=tenant).exists():
            check = StockCheck.all_objects.create(
                tenant=tenant, branch=branch, created_by=pharmacist,
                status=StockCheck.Status.IN_PROGRESS, notes="Month-end count")
            for name, delta in (("Paracetamol 500mg", -12), ("Metformin 500mg", 0),
                                ("Cough syrup 100ml", 2)):
                item = items[name]
                expected = item.quantity_on_hand
                StockCheckItem.all_objects.create(
                    tenant=tenant, stock_check=check, item=item,
                    expected_quantity=expected,
                    actual_quantity=max(expected + delta, 0))
            check.complete(user=manager)
            open_check = StockCheck.all_objects.create(
                tenant=tenant, branch=branch, created_by=nurse,
                status=StockCheck.Status.IN_PROGRESS, notes="Spot check, shelf B")
            for name in ("Amoxicillin 500mg caps", "Salbutamol inhaler"):
                item = items[name]
                StockCheckItem.all_objects.create(
                    tenant=tenant, stock_check=open_check, item=item,
                    expected_quantity=item.quantity_on_hand)
        log("stock checks", StockCheck.all_objects)

        # --- HMO price list + pre-authorisations -----------------------------
        hygeia = HMO.all_objects.get(tenant=tenant, code="HYG")
        member = HmoEnrollment.all_objects.filter(tenant=tenant, hmo=hygeia).first()
        if not HmoItemRule.all_objects.filter(tenant=tenant).exists():
            rules = [("Artemether/Lumefantrine 20/120", "100.00", "1500.00"),
                     ("Amoxicillin 500mg caps", "80.00", None),
                     ("Cough syrup 100ml", "0.00", None),        # excluded
                     ("Ceftriaxone 1g injection", "70.00", "2200.00")]
            for name, pct, tariff in rules:
                HmoItemRule.all_objects.create(
                    tenant=tenant, hmo=hygeia, item=items[name],
                    coverage_percent=Decimal(pct),
                    tariff=Decimal(tariff) if tariff else None)
        if member and not PreAuthorization.all_objects.filter(tenant=tenant).exists():
            def preauth(lines, **kw):
                pa = PreAuthorization.all_objects.create(
                    tenant=tenant, hmo=hygeia, enrollment=member,
                    requested_by=pharmacist, **kw)
                for name, qty in lines:
                    item = items[name]
                    PreAuthorizationItem.all_objects.create(
                        tenant=tenant, authorization=pa, item=item, quantity=qty,
                        amount=item.unit_price * qty)
                pa.amount = sum(i.amount for i in PreAuthorizationItem.all_objects
                                .filter(authorization=pa))
                pa.save(update_fields=["amount", "updated_at"])
                return pa
            preauth([("Ceftriaxone 1g injection", 5)]).approve(
                code="HYG-AUTH-4471", expires_on=today + timedelta(days=14))
            preauth([("Artemether/Lumefantrine 20/120", 3)]).decline(
                "Generic alternative required.")
            preauth([("Amoxicillin 500mg caps", 21), ("Cough syrup 100ml", 1)],
                    notes="Awaiting insurer.")
        log("hmo rules", HmoItemRule.all_objects)
        log("pre-auths", PreAuthorization.all_objects)

        # --- cashiers + payment requests -------------------------------------
        cashier, _ = Cashier.all_objects.get_or_create(
            tenant=tenant, user=manager,
            defaults={"code": "CSH-001", "kind": Cashier.Kind.BOTH})
        Cashier.all_objects.get_or_create(
            tenant=tenant, user=pharmacist,
            defaults={"code": "CSH-002", "kind": Cashier.Kind.RETAIL})
        if not PaymentRequest.all_objects.filter(tenant=tenant).exists():
            def request(lines, **kw):
                pr = PaymentRequest.all_objects.create(
                    tenant=tenant, dispenser=nurse, **kw)
                for name, qty in lines:
                    PaymentRequestItem.all_objects.create(
                        tenant=tenant, request=pr, item=items[name], quantity=qty)
                return pr.recalculate()
            done = request([("Paracetamol 500mg", 12), ("Cough syrup 100ml", 1)],
                           buyer_name="Tunde Adeyemi")
            done.accept(cashier)
            done.complete(user=manager)
            request([("Metformin 500mg", 60)], buyer_name="Aisha Danjuma",
                    notes="Repeat script").accept(cashier)
            request([("Salbutamol inhaler", 1)], buyer_name="Walk-in")
            request([("Ceftriaxone 1g injection", 2)]).reject("Needs a script.")
        log("payment requests", PaymentRequest.all_objects)

        # --- expenses ----------------------------------------------------------
        if not Expense.all_objects.filter(tenant=tenant).exists():
            till = open_till()
            spend = [("Rent", "150000.00", Expense.Source.OTHER, 20, "September rent"),
                     ("Power", "18500.00", Expense.Source.CASH, 3, "Diesel, 50L"),
                     ("Power", "12000.00", Expense.Source.OTHER, 10, "IKEDC bill"),
                     ("Transport", "2500.00", Expense.Source.CASH, 0, "Delivery to Bwari"),
                     ("Cleaning", "4000.00", Expense.Source.CASH, 1, "Weekly clean")]
            for cat, amt, src, ago, desc in spend:
                category, _ = ExpenseCategory.all_objects.get_or_create(
                    tenant=tenant, name=cat)
                Expense.all_objects.create(
                    tenant=tenant, category=category, branch=branch, amount=Decimal(amt),
                    payment_source=src, date=today - timedelta(days=ago),
                    description=desc, created_by=manager,
                    till_session=till if src == Expense.Source.CASH and ago == 0 else None,
                )
        log("expenses", Expense.all_objects)

        # --- notifications ------------------------------------------------------
        # Pre-auth decisions above already notified the counter, so guard on
        # a kind only this block writes.
        if not Notification.all_objects.filter(tenant=tenant, kind="low_stock").exists():
            K, P = Notification.Kind, Notification.Priority
            notes = [
                (pharmacist, K.OUT_OF_STOCK, P.CRITICAL, "ORS sachet out of stock",
                 "Nothing on the shelf; 120 still due on the open order.", "ORS sachet"),
                (pharmacist, K.LOW_STOCK, P.HIGH, "Amoxicillin below reorder level",
                 "40 capsules left against a reorder level of 60.", "Amoxicillin 500mg caps"),
                (manager, K.EXPIRY, P.HIGH, "Metformin batch MF-9 expires in 18 days",
                 "55 tablets to move or write off.", "Metformin 500mg"),
                (manager, K.PAYMENT_REQUEST, P.MEDIUM, "Basket waiting at the till",
                 "Aisha Danjuma, 60 x Metformin 500mg.", None),
                (manager, K.SYSTEM, P.LOW, "Month-end stock check completed",
                 "12 paracetamol written off.", None),
            ]
            for who, kind, prio, title, msg, item in notes:
                Notification.all_objects.create(
                    tenant=tenant, user=who, kind=kind, priority=prio, title=title,
                    message=msg, item=items.get(item))
            Notification.all_objects.filter(tenant=tenant, kind=K.SYSTEM).update(is_read=True)
        log("notifications", Notification.all_objects)

        # --- prescribers, a script that earned them money ----------------------
        if not Prescriber.all_objects.filter(tenant=tenant).exists():
            luth, _ = Hospital.all_objects.get_or_create(
                tenant=tenant, name="Lagos University Teaching Hospital",
                defaults={"city": "Lagos", "phone": "01-2345678",
                          "address": "Idi-Araba, Surulere"})
            Hospital.all_objects.get_or_create(
                tenant=tenant, name="Reddington Hospital",
                defaults={"city": "Lagos", "address": "Victoria Island"})
            dr_okoro = Prescriber.all_objects.create(
                tenant=tenant, hospital=luth, name="Dr. Ifeoma Okoro",
                license_number="MDCN-44127", specialty="Internal medicine",
                phone="08051110001", is_verified=True,
                commission_rate=Decimal("5.00"),
                consult_fee_a=Decimal("2000"), consult_fee_b=Decimal("3500"),
                consult_fee_c=Decimal("5000"), consult_fee_d=Decimal("8000"),
                consult_fee_e=Decimal("12000"))
            Prescriber.all_objects.create(
                tenant=tenant, name="Dr. Yusuf Danladi", specialty="Paediatrics",
                clinic="Danladi Clinic, Kano", license_number="MDCN-51902",
                commission_rate=Decimal("3.00"), consult_fee_a=Decimal("1500"))
            Prescriber.all_objects.create(
                tenant=tenant, name="Dr. Bola Fashola", is_active=False,
                license_number="MDCN-38820", is_verified=False)
            patient = Patient.all_objects.filter(tenant=tenant, first_name="Bola").first()
            rx = Prescription.all_objects.create(
                tenant=tenant, branch=branch, patient=patient,
                customer_name=patient.full_name if patient else "Bola Eze",
                customer_phone="08041110005", prescriber=dr_okoro,
                doctor_name=dr_okoro.name, diagnosis="Community-acquired pneumonia",
                consultation_category="B", created_by=pharmacist,
                source=Prescription.Source.PORTAL)
            amox_line = PrescriptionItem.all_objects.create(
                tenant=tenant, prescription=rx, item=items["Amoxicillin 500mg caps"],
                name="Amoxicillin 500mg caps", quantity=21, dosage="500 mg TID",
                duration="7 days")
            PrescriptionItem.all_objects.create(
                tenant=tenant, prescription=rx, item=items["Cough syrup 100ml"],
                name="Cough syrup 100ml", quantity=1, dosage="10 ml TID",
                duration="5 days")
            # Fill the antibiotic only: PARTIAL, commission on that sale,
            # the consultation fee raised once.
            sale = Sale.all_objects.create(
                tenant=tenant, patient=patient, rx=rx, served_by=pharmacist,
                payment_method=Sale.PaymentMethod.CASH, branch=branch,
                consultation_fee=rx.consultation_fee)
            sale.add_line(amox_line.item, 21, user=pharmacist)
            sale.record_payment(sale.patient_payable, till=open_till(), user=pharmacist)
            amox_line.mark_dispensed(user=pharmacist)
            rx.raise_prescriber_dues(sale)
            # A second, untouched script from the portal so the queue has one.
            pending = Prescription.all_objects.create(
                tenant=tenant, branch=branch, customer_name="Emeka Nwosu",
                customer_phone="08041110006", prescriber=dr_okoro,
                doctor_name=dr_okoro.name, diagnosis="Type 2 diabetes",
                consultation_category="A", source=Prescription.Source.PORTAL)
            PrescriptionItem.all_objects.create(
                tenant=tenant, prescription=pending, item=items["Metformin 500mg"],
                name="Metformin 500mg", quantity=60, dosage="500 mg BID",
                duration="30 days")
        log("prescribers", Prescriber.all_objects)

        # --- staff commission terms ---------------------------------------------
        for who, rate, bonus in ((pharmacist, "2.50", "5000.00"),
                                 (manager, "1.00", None), (nurse, "0.00", None)):
            CommissionConfig.all_objects.get_or_create(
                tenant=tenant, user=who,
                defaults={"rate": Decimal(rate),
                          "fixed_bonus": Decimal(bonus) if bonus else None,
                          "is_active": rate != "0.00"})
        log("commission configs", CommissionConfig.all_objects)

        # --- reader seats: an insurer's claims desk, a state health authority --
        desk, _ = User.objects.get_or_create(
            phone="08061110001",
            defaults={"username": "hygeia-desk", "role": Role.HMO, "tenant": tenant,
                      "hmo": hygeia, "is_admin": True})
        desk.set_password(PASSWORD)
        desk.save()
        lagos = Jurisdiction.objects.filter(name="Lagos", level="state").first()
        gov, _ = User.objects.get_or_create(
            phone="08061110002",
            defaults={"username": "lagos-health", "role": Role.GOVERNMENT,
                      "jurisdiction": lagos, "is_admin": True})
        gov.set_password(PASSWORD)
        gov.save()
        # Hand-made dev accounts with forgotten passwords: put them on the
        # shared one so every seat in the table below can be signed in to.
        for u in User.objects.filter(phone__in=["08070707070", "08012345678"]):
            u.set_password(PASSWORD)
            u.save(update_fields=["password"])

        self.stdout.write(self.style.SUCCESS("seed_ops complete."))
        self.stdout.write(self._logins(tenant))

    @staticmethod
    def _logins(tenant):
        """Every seat a tester can sign in as, with the identifier the login
        form actually wants: licence for clinical cadres, last 6 phone digits
        for pharmacy staff, full phone for everyone else."""
        rows = ["", f"logins (password {PASSWORD!r} unless noted):"]
        live = User.objects.filter(is_active=True)
        seats = list(live.filter(tenant=tenant).order_by("role", "id"))
        seats += list(live.filter(tenant=None, role__in=[
            Role.SUPER_ADMIN, Role.GOVERNMENT]).order_by("id"))
        for u in seats:
            if u.role in LICENSED_ROLES:
                ident = f"licence {u.license_number}"
            elif u.role == Role.PHARMACIST:
                ident = f"code {u.phone[-6:]}"
            else:
                ident = f"phone {u.phone}"
            note = ""
            if u.phone == "08032194090":
                note = "  (password 'nazz2020')"
            elif u.phone.startswith("0803400") or u.phone == "08030000001":
                note = "  (password 'sup3r-secret-pw', scripts/seed_katsina.py)"
            rows.append(f"  {u.role:13} {ident:30} {u.username or '-':16}{note}")
        return chr(10).join(rows)
