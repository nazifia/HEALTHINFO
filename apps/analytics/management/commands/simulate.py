"""Live data simulator. Inserts and mutates random analytics rows on an
interval so real-time dashboards actually move. Ctrl-C to stop.

    python manage.py simulate                 # demo tenant, ~2s/tick
    python manage.py simulate --interval 0.5  # faster
    python manage.py simulate --tenant demo --ticks 100

Needs the catalog already seeded (run `python manage.py seed_dev` first) — it
draws diseases/meds/users from the DB rather than inventing them.

ponytail: one flat loop of random.choice over existing rows. No faker, no
config, no scheduler — Ctrl-C is the off switch. Add weighting/realism only if
a demo actually needs it.
"""
import random
import time

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.analytics.models import (
    AdverseDrugReaction, AnalyticsEvent, Appointment, CaseReport,
    CommunityHealthReport, FacilityMetric, Immunization, InsuranceClaim,
    LabResult, StockReport, VitalEvent,
)
from apps.catalog.models import Disease, Medication, Symptom
from apps.tenants.models import Tenant

REGIONS = ["Ikeja, Lagos", "Kano Municipal, Kano", "Bwari, FCT",
           "Port Harcourt, Rivers", "Nsukka, Enugu"]
AGES = ["0-1", "0-5", "6-12", "13-18", "19-40", "41-60", "60+"]
SEXES = ["M", "F"]
ORGANISMS = ["E. coli", "S. aureus", "K. pneumoniae", "P. aeruginosa"]
ANTIBIOTICS = ["Ciprofloxacin", "Ceftriaxone", "Amoxicillin", "Gentamicin"]
VACCINES = ["BCG", "OPV", "Pentavalent", "Measles", "Yellow Fever", "Tetanus"]
REACTIONS = ["rash", "anaphylaxis", "nausea", "dizziness", "angioedema"]


class Command(BaseCommand):
    help = "Continuously insert/mutate random analytics data (real-time demo)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo", help="Tenant slug.")
        parser.add_argument("--interval", type=float, default=2.0,
                            help="Seconds between ticks (default 2).")
        parser.add_argument("--ticks", type=int, default=0,
                            help="Stop after N ticks (0 = run until Ctrl-C).")

    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(
                f"No tenant '{opts['tenant']}'. Run: python manage.py seed_dev"
            )

        diseases = list(Disease.all_objects.filter(tenant=tenant))
        meds = list(Medication.all_objects.filter(tenant=tenant))
        symptoms = list(Symptom.all_objects.filter(tenant=tenant))
        if not (diseases and meds):
            raise CommandError(
                "Catalog empty for this tenant. Run: python manage.py seed_dev"
            )

        users = {r: self._user(r) for r in
                 (Role.DOCTOR, Role.NURSE, Role.PHARMACIST)}
        doctor = users[Role.DOCTOR] or None

        ctx = dict(tenant=tenant, diseases=diseases, meds=meds,
                   symptoms=symptoms, users=users, doctor=doctor)
        actions = [self._case, self._search, self._view, self._adr, self._lab,
                   self._immunization, self._vital, self._appointment,
                   self._claim, self._facility, self._chw, self._mutate_stock,
                   self._mutate_appointment, self._mutate_claim]

        self.stdout.write(self.style.SUCCESS(
            f"Simulating tenant '{tenant.slug}' every {opts['interval']}s. "
            "Ctrl-C to stop."))
        tick = 0
        try:
            while True:
                tick += 1
                for _ in range(random.randint(1, 3)):
                    msg = random.choice(actions)(**ctx)
                    if msg:
                        self.stdout.write(f"[{tick}] {msg}")
                if opts["ticks"] and tick >= opts["ticks"]:
                    break
                time.sleep(opts["interval"])
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nstopped."))

    # --- helpers ---------------------------------------------------------
    def _user(self, role):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.filter(username=role.value).first()

    def _region(self):
        return random.choice(REGIONS)

    def _age(self):
        return random.choice(AGES)

    # --- inserts ---------------------------------------------------------
    def _case(self, tenant, diseases, meds, symptoms, doctor, **_):
        dis = random.choice(diseases)
        cr = CaseReport.all_objects.create(
            tenant=tenant, reporter=doctor, disease=dis,
            severity=random.choice(CaseReport.Severity.values),
            outcome=random.choice(CaseReport.Outcome.values),
            patient_age_group=self._age(), patient_sex=random.choice(SEXES),
            region=self._region(), notes="simulated",
        )
        if symptoms:
            cr.symptoms.set(random.sample(symptoms, k=min(3, len(symptoms))))
        cr.medications.set([random.choice(meds)])
        return f"case #{cr.pk} {dis.name} ({cr.severity})"

    def _search(self, tenant, doctor, **_):
        q = random.choice(["fever", "malaria", "ibuprofen", "covid vaccine",
                           "asthma", "diabetes", "headache"])
        AnalyticsEvent.all_objects.create(
            tenant=tenant, user=doctor, event_type=AnalyticsEvent.SEARCH,
            query=q, result_count=random.choice([0, 1, 2, 3, 5]),
        )
        return f"search '{q}'"

    def _view(self, tenant, diseases, meds, doctor, **_):
        obj, otype = ((random.choice(diseases), "disease") if random.random() < 0.6
                      else (random.choice(meds), "medication"))
        AnalyticsEvent.all_objects.create(
            tenant=tenant, user=doctor, event_type=AnalyticsEvent.VIEW,
            object_type=otype, object_id=obj.id,
        )
        return f"view {otype} {obj.id}"

    def _adr(self, tenant, meds, doctor, **_):
        adr = AdverseDrugReaction.all_objects.create(
            tenant=tenant, reporter=doctor, medication=random.choice(meds),
            reaction=random.choice(REACTIONS),
            severity=random.choice(AdverseDrugReaction.Severity.values),
            outcome=random.choice(AdverseDrugReaction.Outcome.values),
            patient_age_group=self._age(), patient_sex=random.choice(SEXES),
            region=self._region(),
        )
        return f"ADR #{adr.pk} {adr.reaction}"

    def _lab(self, tenant, diseases, doctor, **_):
        org = random.choice(ORGANISMS)
        lr = LabResult.all_objects.create(
            tenant=tenant, reporter=doctor,
            disease=random.choice(diseases) if random.random() < 0.5 else None,
            organism=org, antibiotic=random.choice(ANTIBIOTICS),
            susceptibility=random.choice(LabResult.Susceptibility.values),
            flag=random.choice(LabResult.Flag.values), value="culture + AST",
            patient_age_group=self._age(), patient_sex=random.choice(SEXES),
            region=self._region(),
        )
        return f"lab #{lr.pk} {org}/{lr.susceptibility}"

    def _immunization(self, tenant, users, **_):
        vac = random.choice(VACCINES)
        Immunization.all_objects.create(
            tenant=tenant, reporter=users.get(Role.NURSE), vaccine=vac,
            dose_number=random.randint(1, 3), patient_age_group=self._age(),
            patient_sex=random.choice(SEXES), region=self._region(),
        )
        return f"immunization {vac}"

    def _vital(self, tenant, diseases, users, doctor, **_):
        if random.random() < 0.7:
            VitalEvent.all_objects.create(
                tenant=tenant, reporter=users.get(Role.NURSE),
                event_type=VitalEvent.Kind.BIRTH, patient_age_group="0-1",
                region=self._region(),
            )
            return "birth"
        infant = random.random() < 0.3
        VitalEvent.all_objects.create(
            tenant=tenant, reporter=doctor, event_type=VitalEvent.Kind.DEATH,
            cause=random.choice(diseases), maternal_death=random.random() < 0.1,
            infant_death=infant, patient_age_group="0-1" if infant else self._age(),
            region=self._region(),
        )
        return "death"

    def _appointment(self, tenant, doctor, **_):
        ap = Appointment.all_objects.create(
            tenant=tenant, reporter=doctor,
            mode=random.choice(Appointment.Mode.values),
            status=random.choice(Appointment.Status.values),
            reason="Follow-up", patient_age_group=self._age(),
            region=self._region(),
        )
        return f"appt #{ap.pk} {ap.mode}/{ap.status}"

    def _claim(self, tenant, diseases, users, **_):
        cl = InsuranceClaim.all_objects.create(
            tenant=tenant, reporter=users.get(Role.PHARMACIST),
            diagnosis=random.choice(diseases),
            amount=random.randint(5, 80) * 1000,
            status=random.choice(InsuranceClaim.Status.values),
            patient_age_group=self._age(), region=self._region(),
        )
        return f"claim #{cl.pk} {cl.amount} ({cl.status})"

    def _facility(self, tenant, doctor, **_):
        total = 100
        occ = random.randint(55, 95)
        FacilityMetric.all_objects.create(
            tenant=tenant, reporter=doctor, beds_total=total, beds_occupied=occ,
            avg_wait_minutes=random.randint(20, 60),
            staff_on_duty=random.randint(12, 22),
            patients_treated=random.randint(50, 90), region=self._region(),
        )
        return f"facility occ {occ}%"

    def _chw(self, tenant, users, **_):
        kind = random.choice(CommunityHealthReport.Kind.values)
        CommunityHealthReport.all_objects.create(
            tenant=tenant, reporter=users.get(Role.NURSE), report_type=kind,
            danger_signs=random.random() < 0.3, referred=random.random() < 0.4,
            patient_age_group=self._age(), region=self._region(),
        )
        return f"chw {kind}"

    # --- mutations (the "manipulated real-time" part) --------------------
    def _mutate_stock(self, tenant, meds, users, **_):
        """Consume/restock a medication so stock + shortage flags move live."""
        sr = StockReport.all_objects.filter(tenant=tenant).order_by("?").first()
        if sr is None:
            sr = StockReport.all_objects.create(
                tenant=tenant, reporter=users.get(Role.PHARMACIST),
                medication=random.choice(meds), on_hand=random.randint(0, 300),
                consumed=0, region=self._region(),
            )
        used = random.randint(0, 40)
        restock = random.randint(0, 60) if random.random() < 0.3 else 0
        sr.on_hand = max(0, sr.on_hand - used + restock)
        sr.consumed += used
        sr.shortage = sr.on_hand < 20
        sr.save(update_fields=["on_hand", "consumed", "shortage", "updated_at"])
        return f"stock #{sr.pk} on_hand={sr.on_hand}{' SHORT' if sr.shortage else ''}"

    def _mutate_appointment(self, tenant, **_):
        """Advance a scheduled appointment to a final state."""
        ap = (Appointment.all_objects
              .filter(tenant=tenant, status=Appointment.Status.SCHEDULED)
              .order_by("?").first())
        if ap is None:
            return None
        ap.status = random.choice([Appointment.Status.COMPLETED,
                                   Appointment.Status.NO_SHOW,
                                   Appointment.Status.CANCELLED])
        ap.save(update_fields=["status", "updated_at"])
        return f"appt #{ap.pk} -> {ap.status}"

    def _mutate_claim(self, tenant, **_):
        """Move a submitted claim through the adjudication lifecycle."""
        cl = (InsuranceClaim.all_objects
              .filter(tenant=tenant, status=InsuranceClaim.Status.SUBMITTED)
              .order_by("?").first())
        if cl is None:
            return None
        cl.status = random.choice([InsuranceClaim.Status.APPROVED,
                                   InsuranceClaim.Status.REJECTED,
                                   InsuranceClaim.Status.PAID])
        cl.save(update_fields=["status", "updated_at"])
        return f"claim #{cl.pk} -> {cl.status}"
