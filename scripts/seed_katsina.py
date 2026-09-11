"""Seed one state's worth of data so a Katsina health authority has rollups to read.

Run: python manage.py shell -c "exec(open('scripts/seed_katsina.py').read())"

Two Katsina facilities (Daura hospital, Funtua pharmacy) with cases, sales,
prescriptions and a controlled-drug line; a Kano pharmacy beside them so the
fence shows — the Katsina seat must never see Kano's rows. Re-runnable:
looks rows up by slug/phone before creating them.
"""
from datetime import timedelta
from decimal import Decimal
import random

from django.utils import timezone

from apps.accounts.models import Role, User
from apps.analytics.models import (
    AdverseDrugReaction, AnalyticsEvent, Appointment, CaseReport,
    CommunityHealthReport, Consultation, FacilityMetric, Immunization,
    InsuranceClaim, LabResult, Prescription as RxOrder, StockReport, VitalEvent,
)
from apps.catalog.models import Disease, LabTest, Medication
from apps.patients.models import Patient
from apps.inventory.models import StockItem
from apps.pos.models import Sale, SaleItem
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.tenants.models import Jurisdiction, Tenant

random.seed(7)
PW = "sup3r-secret-pw"
now = timezone.now()

katsina = Jurisdiction.objects.get(name="Katsina", level="state")
kano = Jurisdiction.objects.get(name="Kano", level="state")
lga = lambda state, name: Jurisdiction.objects.get(parent=state, name__iexact=name)

def tenant(slug, name, kind, patch):
    t, _ = Tenant.objects.get_or_create(slug=slug, defaults=dict(
        name=name, kind=kind, jurisdiction=patch))
    return t

def seat(phone, role, **kw):
    u = User.objects.filter(phone=phone).first()
    if u is None:
        u = User.objects.create_user(phone=phone, password=PW, role=role, **kw)
    else:
        for k, v in kw.items(): setattr(u, k, v)
        u.role = role; u.set_password(PW); u.save()
    return u

daura = tenant("daura-gh", "Daura General Hospital", "hospital", lga(katsina, "Daura"))
funtua = tenant("funtua-rx", "Funtua Central Pharmacy", "pharmacy", lga(katsina, "Funtua"))
kano_rx = tenant("kano-rx", "Kano Municipal Pharmacy", "pharmacy", lga(kano, "Kano Municipal"))

gov = seat("08030000001", Role.GOVERNMENT, jurisdiction=katsina, tenant=None, is_admin=True)
seat("08034000001", Role.TENANT_ADMIN, tenant=daura)
seat("08034000002", Role.DOCTOR, tenant=daura)
seat("08034000003", Role.TENANT_ADMIN, tenant=funtua)
seat("08034000004", Role.PHARMACIST, tenant=funtua)
seat("08034000009", Role.TENANT_ADMIN, tenant=kano_rx)

# -- cases: a month of background noise, plus a cholera spike today in Daura
diseases = list(Disease.objects.filter(
    name__in=["Malaria", "Cholera", "Measles", "Typhoid Fever", "Gastroenteritis"]))
cholera = Disease.objects.filter(name="Cholera").first()

def cases(t, n, disease, days_ago):
    for _ in range(n):
        r = CaseReport.all_objects.create(
            tenant=t, disease=disease, region=t.jurisdiction.name,
            severity=random.choice([c.value for c in CaseReport.Severity]))
        CaseReport.all_objects.filter(pk=r.pk).update(
            created_at=now - timedelta(days=days_ago, hours=0 if days_ago == 0 else random.randint(0, 20)))

if not CaseReport.all_objects.filter(tenant=daura).exists():
    for d in range(29, 0, -1):
        cases(daura, random.randint(0, 2), random.choice(diseases), d)
        cases(funtua, random.randint(0, 1), random.choice(diseases), d)
        cases(kano_rx, random.randint(0, 2), random.choice(diseases), d)
    if cholera: cases(daura, 8, cholera, 0)        # today's spike
    cases(funtua, 2, random.choice(diseases), 0)

# -- stock, sales, scripts
def item(t, name, price, controlled=False):
    i, _ = StockItem.all_objects.get_or_create(tenant=t, name=name, defaults=dict(
        unit="tablet", is_controlled=controlled,
        cost_price=price / 2, unit_price=price))
    return i

def trade(t, stock):
    if Sale.all_objects.filter(tenant=t).exists():
        return
    for d in range(60):
        for _ in range(random.randint(1, 4)):
            s = Sale.all_objects.create(tenant=t, status=Sale.Status.PAID)
            total = Decimal(0)
            for st in random.sample(stock, k=random.randint(1, 2)):
                q = random.randint(1, 5)
                SaleItem.all_objects.create(
                    tenant=t, sale=s, item=st, name=st.name, quantity=q,
                    unit_price=st.unit_price, cost_price=st.cost_price)
                total += st.unit_price * q
            when = now - timedelta(days=d, hours=random.randint(1, 12))
            Sale.all_objects.filter(pk=s.pk).update(total=total, created_at=when)
    for st in stock:
        if st.is_controlled:
            rx = Prescription.all_objects.create(tenant=t, customer_name="Walk-in")
            PrescriptionItem.all_objects.create(
                tenant=t, prescription=rx, item=st, name=st.name,
                quantity=random.randint(2, 6), is_dispensed=True)

for t in (funtua, daura, kano_rx):
    trade(t, [
        item(t, "Paracetamol 500mg", Decimal("500.00")),
        item(t, "Artemether/Lumefantrine", Decimal("2500.00")),
        item(t, "Amoxicillin 500mg", Decimal("1200.00")),
        item(t, "Tramadol 100mg", Decimal("800.00"), controlled=True),
        item(t, "Codeine syrup", Decimal("1500.00"), controlled=True),
    ])

# -- the clinical feeds: everything else the rollups read
def backdate(model, pk, days_ago):
    model.all_objects.filter(pk=pk).update(
        created_at=now - timedelta(days=days_ago, hours=random.randint(0, 6)))

def clinical(t, reporter):
    if Patient.all_objects.filter(tenant=t).exists():
        return
    meds = list(Medication.objects.all()[:12])
    tests = list(LabTest.objects.all())
    ill = list(Disease.objects.all())
    names = ["Aisha", "Musa", "Fatima", "Sani", "Hauwa", "Bello", "Zainab", "Umar"]
    patients = [Patient.all_objects.create(
        tenant=t, first_name=random.choice(names), last_name=random.choice(
            ["Lawal", "Abdullahi", "Yusuf", "Ibrahim", "Danjuma"]),
        sex=random.choice(["M", "F"]), region=t.jurisdiction.name,
        date_of_birth=now.date() - timedelta(days=random.randint(200, 25000)),
        registered_by=reporter) for _ in range(12)]
    pat = lambda: random.choice(patients)
    # The cases above were filed before the register existed: give each one
    # a patient so the sex and age-band breakdowns have something to say.
    for c in CaseReport.all_objects.filter(tenant=t, patient=None):
        c.patient = pat(); c.save()
    cases = list(CaseReport.all_objects.filter(tenant=t))
    still_open = set()   # a patient carries at most one open consultation
    for d in range(45, -1, -1):
        for _ in range(random.randint(1, 3)):
            case = random.choice(cases) if cases and random.random() < 0.7 else None
            rx = RxOrder.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter, case_report=case,
                medication=random.choice(meds), dose="1 tab", frequency="bd",
                duration_days=random.choice([3, 5, 7]), region=t.jurisdiction.name,
                status=random.choices(
                    [c.value for c in RxOrder.Status], [3, 1, 8, 1])[0])
            backdate(RxOrder, rx.pk, d)
        if random.random() < 0.3:
            adr = AdverseDrugReaction.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter,
                medication=random.choice(meds), region=t.jurisdiction.name,
                reaction=random.choice(["rash", "nausea", "dizziness", "anaphylaxis"]),
                severity=random.choice([c.value for c in AdverseDrugReaction.Severity]),
                outcome=random.choice([c.value for c in AdverseDrugReaction.Outcome]))
            backdate(AdverseDrugReaction, adr.pk, d)
        for _ in range(random.randint(0, 2)):
            amr = random.random() < 0.4
            lab = LabResult.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter,
                lab_test=random.choice(tests), disease=random.choice(ill),
                value=str(random.randint(3, 15)), region=t.jurisdiction.name,
                flag=random.choice([c.value for c in LabResult.Flag]),
                organism=random.choice(["E. coli", "S. aureus", "Klebsiella"]) if amr else "",
                antibiotic=random.choice(["Ciprofloxacin", "Amoxicillin", "Ceftriaxone"]) if amr else "",
                susceptibility=random.choice(
                    [c.value for c in LabResult.Susceptibility]) if amr else "")
            backdate(LabResult, lab.pk, d)
        if random.random() < 0.5:
            chw = CommunityHealthReport.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter, region=t.jurisdiction.name,
                report_type=random.choice(["pregnancy", "newborn", "malnutrition", "death", "other"]),
                danger_signs=random.random() < 0.2, referred=random.random() < 0.3)
            backdate(CommunityHealthReport, chw.pk, d)
        if t.kind == "hospital":
            fm = FacilityMetric.all_objects.create(
                tenant=t, reporter=reporter, beds_total=60, region=t.jurisdiction.name,
                beds_occupied=random.randint(25, 58), avg_wait_minutes=random.randint(15, 90),
                staff_on_duty=random.randint(8, 20), patients_treated=random.randint(30, 120))
            backdate(FacilityMetric, fm.pk, d)
        if random.random() < 0.6:
            claim = InsuranceClaim.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter, diagnosis=random.choice(ill),
                amount=Decimal(random.randint(2, 60) * 500), region=t.jurisdiction.name,
                status=random.choice([c.value for c in InsuranceClaim.Status]))
            backdate(InsuranceClaim, claim.pk, d)
        for _ in range(random.randint(1, 3)):
            appt = Appointment.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter, region=t.jurisdiction.name,
                mode=random.choices(["in_person", "telemedicine"], [4, 1])[0],
                status=random.choices(["scheduled", "completed", "no_show", "cancelled"],
                                      [1, 6, 1, 1])[0],
                reason=random.choice(["fever", "follow-up", "antenatal", "check-up"]))
            backdate(Appointment, appt.pk, d)
            if appt.status == "completed":
                closed = random.random() < 0.8 or appt.patient.pk in still_open
                if not closed: still_open.add(appt.patient.pk)
                c = Consultation.all_objects.create(
                    tenant=t, patient=appt.patient, reporter=reporter, appointment=appt,
                    case_report=random.choice(cases) if cases and random.random() < 0.5 else None,
                    chief_complaint=appt.reason, region=t.jurisdiction.name,
                    temperature_c=Decimal(str(round(random.uniform(36.2, 39.5), 1))),
                    pulse_bpm=random.randint(60, 120), respiratory_rate=random.randint(12, 28),
                    systolic_bp=random.randint(95, 170), diastolic_bp=random.randint(60, 105),
                    oxygen_saturation=random.randint(90, 99),
                    weight_kg=Decimal(random.randint(8, 95)), height_cm=Decimal(random.randint(70, 185)),
                    status="closed" if closed else "open",
                    disposition=random.choices(
                        ["home", "follow_up", "admitted", "referred", "deceased"],
                        [6, 3, 2, 1, 0.2])[0] if closed else "",
                    closed_at=now - timedelta(days=d) if closed else None)
                backdate(Consultation, c.pk, d)
        if random.random() < 0.7:
            imm = Immunization.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter, region=t.jurisdiction.name,
                vaccine=random.choice(["BCG", "OPV", "Penta", "Measles", "Yellow Fever", "HPV"]),
                dose_number=random.randint(1, 3))
            backdate(Immunization, imm.pk, d)
        if random.random() < 0.4:
            death = random.random() < 0.3
            ve = VitalEvent.all_objects.create(
                tenant=t, patient=pat(), reporter=reporter, region=t.jurisdiction.name,
                event_type="death" if death else "birth",
                cause=random.choice(ill) if death else None,
                maternal_death=death and random.random() < 0.2,
                infant_death=death and random.random() < 0.3)
            backdate(VitalEvent, ve.pk, d)
        if d % 7 == 0:
            for m in random.sample(meds, 4):
                on_hand = random.randint(0, 400)
                sr = StockReport.all_objects.create(
                    tenant=t, reporter=reporter, medication=m, on_hand=on_hand,
                    consumed=random.randint(10, 200), shortage=on_hand < 30,
                    region=t.jurisdiction.name)
                backdate(StockReport, sr.pk, d)
        for _ in range(random.randint(0, 4)):
            ev = AnalyticsEvent.all_objects.create(
                tenant=t, user=reporter, event_type="search",
                query=random.choice(["malaria", "cholera", "paracetamol", "bp", "typhoid"]),
                result_count=random.choice([0, 0, 3, 8]))
            backdate(AnalyticsEvent, ev.pk, d)
    # IDSR: the immediate-notification worklist — one cholera case sent on
    # time, the rest still owed.
    urgent = CaseReport.all_objects.filter(tenant=t, disease__notify_immediately=True)
    first = urgent.first()
    if first:
        CaseReport.all_objects.filter(pk=first.pk).update(
            notified_at=first.created_at + timedelta(hours=5), notified_by=reporter)

clinical(daura, User.objects.get(phone="08034000002"))
clinical(funtua, User.objects.get(phone="08034000004"))
clinical(kano_rx, User.objects.get(phone="08034000009"))

print(f"government seat {gov.phone} / {PW} -> {gov.jurisdiction}")
for t in (daura, funtua, kano_rx):
    print(t.slug, t.jurisdiction, "cases", CaseReport.all_objects.filter(tenant=t).count(),
          "sales", Sale.all_objects.filter(tenant=t).count())
