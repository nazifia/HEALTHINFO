"""Dev seed data. Idempotent: re-runnable, get_or_create everywhere.

    python manage.py seed_dev

Creates one tenant, an admin + per-role users, and a small connected catalog
(symptoms, diseases, meds, an interaction, specialty/procedure/lab/article).
Passes tenant= explicitly so it works without the request middleware bound.

ponytail: single hard-coded tenant + handful of rows. Enough to click through
the app. Add --tenant / --count flags only if someone actually needs them.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role
from apps.catalog.models import (
    Article, Disease, DrugInteraction, LabTest, Medication, Procedure,
    Specialty, Status, Symptom,
)
from apps.tenants.models import Tenant
from apps.analytics.models import AnalyticsEvent

User = get_user_model()

PASSWORD = "devpass123"  # ponytail: dev-only shared password, never ships to prod


class Command(BaseCommand):
    help = "Seed development data (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=0,
            help="Extra synthetic diseases+meds to generate (default 0).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        tenant, _ = Tenant.objects.get_or_create(
            slug="demo",
            defaults={"name": "Demo Clinic", "domain": "demo.localhost"},
        )
        self.stdout.write(f"tenant: {tenant}")

        # Users: one per role + the platform super-admin.
        User.objects.get_or_create(
            username="superadmin",
            defaults={
                "phone": "+2348000000000",
                "role": Role.SUPER_ADMIN, "is_staff": True, "is_superuser": True,
                "email": "super@demo.localhost",
            },
        )[0].set_password(PASSWORD)  # noqa: ensure pw set below
        for i, role in enumerate([Role.TENANT_ADMIN, Role.DOCTOR, Role.PHARMACIST,
                                  Role.NURSE, Role.PUBLIC], start=1):
            u, _ = User.objects.get_or_create(
                username=role.value,
                defaults={"phone": f"+234800000000{i}", "role": role,
                          "tenant": tenant,
                          "email": f"{role.value}@demo.localhost"},
            )
            u.set_password(PASSWORD)
            u.save()
        # Reset super-admin pw too (get_or_create above didn't save the hash).
        su = User.objects.get(username="superadmin")
        su.set_password(PASSWORD)
        su.save()

        # Named platform admin (real login used in dev). Own password, not the
        # shared dev one. ponytail: hardcoded dev creds, never ships to prod.
        nazz, _ = User.objects.get_or_create(
            phone="08032194090",
            defaults={
                "username": "nazz", "role": Role.SUPER_ADMIN,
                "is_staff": True, "is_superuser": True,
                "email": "nazz@demo.localhost",
            },
        )
        nazz.set_password("nazz2020")
        nazz.save()

        self.stdout.write(f"users: {User.objects.count()} (password '{PASSWORD}')")

        def co(model, defaults=None, **lookup):
            """get_or_create scoped to tenant, bypassing the thread-local."""
            return model.all_objects.get_or_create(
                tenant=tenant, defaults=defaults or {}, **lookup
            )[0]

        fever = co(Symptom, {"severity_level": 3}, name="Fever")
        cough = co(Symptom, {"severity_level": 2}, name="Cough")
        headache = co(Symptom, {"severity_level": 2}, name="Headache")
        # Common clinical symptoms so the case form + disease detail look real.
        sore_throat = co(Symptom, {"severity_level": 2}, name="Sore throat")
        fatigue = co(Symptom, {"severity_level": 1}, name="Fatigue")
        dyspnea = co(Symptom, {"severity_level": 4}, name="Shortness of breath")
        chest_pain = co(Symptom, {"severity_level": 4}, name="Chest pain")
        nausea = co(Symptom, {"severity_level": 2}, name="Nausea")
        diarrhea = co(Symptom, {"severity_level": 2}, name="Diarrhea")
        rash = co(Symptom, {"severity_level": 2}, name="Rash")
        dizziness = co(Symptom, {"severity_level": 2}, name="Dizziness")
        myalgia = co(Symptom, {"severity_level": 2}, name="Muscle aches")
        runny_nose = co(Symptom, {"severity_level": 1}, name="Runny nose")

        amox = co(Medication, {
            "brand_name": "Amoxil", "drug_class": "Penicillin antibiotic",
            "indications": "Bacterial infections.", "dosage": "500mg TID",
            "status": Status.PUBLISHED,
        }, generic_name="Amoxicillin")
        ibu = co(Medication, {
            "brand_name": "Advil", "drug_class": "NSAID",
            "indications": "Pain, fever, inflammation.", "dosage": "400mg q6h",
            "status": Status.PUBLISHED,
        }, generic_name="Ibuprofen")
        warfarin = co(Medication, {
            "brand_name": "Coumadin", "drug_class": "Anticoagulant",
            "indications": "Clot prevention.", "dosage": "Per INR",
            "status": Status.PUBLISHED,
        }, generic_name="Warfarin")
        paracetamol = co(Medication, {
            "brand_name": "Panadol", "drug_class": "Analgesic / antipyretic",
            "indications": "Pain and fever.", "dosage": "500-1000mg q6h",
            "status": Status.PUBLISHED,
        }, generic_name="Paracetamol")
        metformin = co(Medication, {
            "brand_name": "Glucophage", "drug_class": "Biguanide antidiabetic",
            "indications": "Type 2 diabetes.", "dosage": "500-1000mg BID",
            "status": Status.PUBLISHED,
        }, generic_name="Metformin")
        lisinopril = co(Medication, {
            "brand_name": "Zestril", "drug_class": "ACE inhibitor",
            "indications": "Hypertension, heart failure.", "dosage": "10-40mg daily",
            "status": Status.PUBLISHED,
        }, generic_name="Lisinopril")
        salbutamol = co(Medication, {
            "brand_name": "Ventolin", "drug_class": "Short-acting beta agonist",
            "indications": "Asthma, bronchospasm.", "dosage": "100-200mcg PRN",
            "status": Status.PUBLISHED,
        }, generic_name="Salbutamol")
        artemether = co(Medication, {
            "brand_name": "Coartem", "drug_class": "Antimalarial",
            "indications": "Uncomplicated falciparum malaria.",
            "dosage": "Weight-based, 3-day course", "status": Status.PUBLISHED,
        }, generic_name="Artemether-Lumefantrine")

        DrugInteraction.all_objects.get_or_create(
            tenant=tenant, medication_a=ibu, medication_b=warfarin,
            defaults={
                "severity": DrugInteraction.Severity.MAJOR,
                "description": "NSAIDs increase bleeding risk with anticoagulants.",
                "recommendation": "Avoid; prefer acetaminophen.",
            },
        )

        flu = co(Disease, {
            "name": "Influenza", "icd10_code": "J10",
            "description": "Viral respiratory infection.",
            "treatment": "Rest, fluids, antivirals.", "status": Status.PUBLISHED,
        }, slug="influenza")
        strep = co(Disease, {
            "name": "Strep Throat", "icd10_code": "J02.0",
            "description": "Bacterial pharyngitis.",
            "treatment": "Antibiotics.", "status": Status.PUBLISHED,
        }, slug="strep-throat")

        flu.symptoms.set([fever, cough, headache])
        strep.symptoms.set([fever, headache])
        flu.medications.set([ibu])
        strep.medications.set([amox])

        resp = co(Specialty, {"description": "Respiratory system."},
                  name="Pulmonology")
        resp.diseases.set([flu, strep])

        co(Procedure, {
            "name": "Throat Swab", "description": "Sample for strep culture.",
            "status": Status.PUBLISHED,
        }, slug="throat-swab").diseases.set([strep])

        co(LabTest, {
            "name": "Rapid Strep Test", "purpose": "Detect group A strep antigen.",
            "normal_range": "Negative", "status": Status.PUBLISHED,
        }, slug="rapid-strep-test").diseases.set([strep])

        art = co(Article, {
            "title": "Managing Seasonal Flu",
            "summary": "Self-care and when to see a doctor.",
            "body": "Most cases resolve with rest and fluids.",
            "status": Status.PUBLISHED,
        }, slug="managing-seasonal-flu")
        art.diseases.set([flu])
        art.medications.set([ibu])

        # More real diseases so catalog/graph/case picker look populated.
        htn = co(Disease, {
            "name": "Hypertension", "icd10_code": "I10",
            "description": "Persistently elevated arterial blood pressure.",
            "treatment": "Lifestyle change, ACE inhibitors, diuretics.",
            "status": Status.PUBLISHED,
        }, slug="hypertension")
        htn.symptoms.set([headache, dizziness, chest_pain])
        htn.medications.set([lisinopril])

        dm2 = co(Disease, {
            "name": "Type 2 Diabetes", "icd10_code": "E11",
            "description": "Insulin resistance causing chronic hyperglycemia.",
            "treatment": "Diet, metformin, glucose monitoring.",
            "status": Status.PUBLISHED,
        }, slug="type-2-diabetes")
        dm2.symptoms.set([fatigue, dizziness])
        dm2.medications.set([metformin])

        asthma = co(Disease, {
            "name": "Asthma", "icd10_code": "J45",
            "description": "Chronic airway inflammation with reversible obstruction.",
            "treatment": "Inhaled bronchodilators and corticosteroids.",
            "status": Status.PUBLISHED,
        }, slug="asthma")
        asthma.symptoms.set([cough, dyspnea, chest_pain])
        asthma.medications.set([salbutamol])

        malaria = co(Disease, {
            "name": "Malaria", "icd10_code": "B54",
            "description": "Mosquito-borne Plasmodium infection.",
            "treatment": "Artemisinin-based combination therapy.",
            "status": Status.PUBLISHED,
        }, slug="malaria")
        malaria.symptoms.set([fever, headache, myalgia, nausea])
        malaria.medications.set([artemether, paracetamol])

        gastro = co(Disease, {
            "name": "Gastroenteritis", "icd10_code": "A09",
            "description": "Inflammation of the GI tract, usually infectious.",
            "treatment": "Oral rehydration, supportive care.",
            "status": Status.PUBLISHED,
        }, slug="gastroenteritis")
        gastro.symptoms.set([nausea, diarrhea, fever])
        gastro.medications.set([paracetamol])

        resp.diseases.add(asthma)
        co(Specialty, {"description": "Heart and vessels."},
           name="Cardiology").diseases.set([htn])
        co(Specialty, {"description": "Hormones and metabolism."},
           name="Endocrinology").diseases.set([dm2])

        co(Article, {
            "title": "Living with Type 2 Diabetes",
            "summary": "Daily management, diet, and monitoring.",
            "body": "Consistent glucose control prevents long-term complications.",
            "status": Status.PUBLISHED,
        }, slug="living-with-type-2-diabetes").diseases.set([dm2])
        co(Article, {
            "title": "Recognising an Asthma Attack",
            "summary": "Warning signs and reliever-inhaler use.",
            "body": "Seek help when a reliever no longer controls breathlessness.",
            "status": Status.PUBLISHED,
        }, slug="recognising-an-asthma-attack").diseases.set([asthma])

        # Realistic case reports so the cases + collated reports screens have
        # content. No natural unique key, so notes doubles as the idempotency key.
        from apps.analytics.models import CaseReport, AiInteraction
        doctor = User.objects.get(username=Role.DOCTOR.value)
        nurse = User.objects.get(username=Role.NURSE.value)
        if True:  # ponytail: kept flat; block scopes the long specs list
            specs = [
                (flu, "moderate", "recovered", "6-12", "F", [fever, cough, headache],
                 [ibu], doctor, "Febrile 3 days, resolved with supportive care."),
                (strep, "mild", "recovered", "13-18", "M", [fever, sore_throat],
                 [amox], doctor, "Rapid strep positive, started amoxicillin."),
                (malaria, "severe", "referred", "19-40", "M",
                 [fever, headache, myalgia], [artemether], doctor,
                 "High parasitemia, referred to district hospital."),
                (asthma, "moderate", "ongoing", "19-40", "F", [dyspnea, cough],
                 [salbutamol], nurse, "Exacerbation, responded to nebulised salbutamol."),
                (htn, "moderate", "ongoing", "60+", "M", [headache, dizziness],
                 [lisinopril], doctor, "BP 168/98, commenced lisinopril."),
                (dm2, "mild", "ongoing", "41-60", "F", [fatigue],
                 [metformin], doctor, "HbA1c 8.1%, lifestyle advice + metformin."),
                (gastro, "mild", "recovered", "0-5", "M", [diarrhea, nausea, fever],
                 [paracetamol], nurse, "Mild dehydration, ORS at home."),
                (flu, "mild", "recovered", "41-60", "F", [fever, myalgia, runny_nose],
                 [paracetamol], nurse, "Seasonal flu, symptomatic management."),
                (malaria, "moderate", "recovered", "6-12", "F",
                 [fever, nausea], [artemether], doctor, "Uncomplicated, completed ACT."),
                (asthma, "critical", "referred", "13-18", "M",
                 [dyspnea, chest_pain], [salbutamol], doctor,
                 "Silent chest, blue-light transfer to ED."),
                (gastro, "moderate", "recovered", "19-40", "F",
                 [diarrhea, fever, nausea], [paracetamol], nurse,
                 "Food-borne, IV fluids then discharged."),
                (htn, "severe", "referred", "60+", "F", [chest_pain, dyspnea],
                 [lisinopril], doctor, "Hypertensive urgency, cardiology referral."),
            ]
            made = 0
            for dis, sev, out, age, sex, syms, meds, who, note in specs:
                # notes is unique per spec → use it as the idempotency key.
                cr, created = CaseReport.all_objects.get_or_create(
                    tenant=tenant, notes=note,
                    defaults={"reporter": who, "disease": dis, "severity": sev,
                              "outcome": out, "patient_age_group": age,
                              "patient_sex": sex},
                )
                if created:
                    cr.symptoms.set(syms)
                    cr.medications.set(meds)
                    made += 1
            self.stdout.write(f"case reports: +{made} (total target {len(specs)})")

        # AI Q&A history so ask analytics / audits aren't empty.
        if not AiInteraction.all_objects.filter(tenant=tenant).exists():
            qa = [
                ("What are the symptoms of malaria?",
                 "Common symptoms include fever, headache, muscle aches and nausea. "
                 "Seek testing promptly in endemic areas.", "up"),
                ("Can I take ibuprofen with warfarin?",
                 "No — NSAIDs like ibuprofen raise bleeding risk with anticoagulants. "
                 "Prefer paracetamol and consult the prescriber.", "up"),
                ("First-line treatment for type 2 diabetes?",
                 "Lifestyle modification plus metformin is first-line unless "
                 "contraindicated.", "up"),
                ("How is strep throat diagnosed?",
                 "A rapid antigen test or throat culture confirms group A strep.", ""),
                ("What relieves an acute asthma attack?",
                 "A short-acting beta agonist such as salbutamol is the reliever of "
                 "choice; escalate if no response.", "down"),
                ("Normal blood pressure range?",
                 "Below 120/80 mmHg is considered normal for most adults.", "up"),
            ]
            for q, a, fb in qa:
                AiInteraction.all_objects.create(
                    tenant=tenant, user=doctor, question=q, answer=a,
                    model_name="seed-demo", feedback=fb, sources=[],
                )
            self.stdout.write(f"ai interactions: {len(qa)}")

        # Synthetic bulk rows for list/pagination/search testing.
        n = opts["count"]
        for i in range(1, n + 1):
            d = co(Disease, {
                "name": f"Test Disease {i}", "description": "Synthetic seed row.",
                "status": Status.PUBLISHED,
            }, slug=f"test-disease-{i}")
            m = co(Medication, {
                "drug_class": "Test class", "indications": "Synthetic seed row.",
                "status": Status.PUBLISHED,
            }, generic_name=f"Test Drug {i}")
            d.medications.set([m])
            d.symptoms.set([fever])
        if n:
            self.stdout.write(f"synthetic: {n} diseases + {n} meds")

        # Analytics events so the dashboard isn't all zeros. No unique key on
        # the table, so guard on existence to stay idempotent.
        doctor = User.objects.get(username=Role.DOCTOR.value)
        if not AnalyticsEvent.all_objects.filter(tenant=tenant).exists():
            ev = []
            # Searches with hits (top searches).
            for q, c in [("flu", 5), ("fever", 3), ("ibuprofen", 2)]:
                ev += [AnalyticsEvent(tenant=tenant, user=doctor,
                                      event_type=AnalyticsEvent.SEARCH,
                                      query=q, result_count=3) for _ in range(c)]
            # Searches with no hits (content gaps).
            for q, c in [("covid vaccine", 4), ("malaria", 2)]:
                ev += [AnalyticsEvent(tenant=tenant, user=doctor,
                                      event_type=AnalyticsEvent.SEARCH,
                                      query=q, result_count=0) for _ in range(c)]
            # Content views (popular diseases / medications).
            for obj, otype, c in [(flu, "disease", 8), (strep, "disease", 3),
                                  (ibu, "medication", 6), (amox, "medication", 2)]:
                ev += [AnalyticsEvent(tenant=tenant, user=doctor,
                                      event_type=AnalyticsEvent.VIEW,
                                      object_type=otype, object_id=obj.id)
                       for _ in range(c)]
            AnalyticsEvent.all_objects.bulk_create(ev)
            self.stdout.write(f"analytics: {len(ev)} events")

        # Public-health feeds: lab/AMR, immunization, vital events, stock.
        # Each guarded on existence (no natural unique key) to stay idempotent.
        from apps.analytics.models import (
            Immunization, LabResult, StockReport, VitalEvent,
        )
        # Valid "LGA, State" regions so the by-state rollups have content.
        regions = ["Ikeja, Lagos", "Kano Municipal, Kano", "Bwari, FCT",
                   "Port Harcourt, Rivers"]
        rapid_strep = LabTest.all_objects.filter(
            tenant=tenant, slug="rapid-strep-test"
        ).first()

        if not LabResult.all_objects.filter(tenant=tenant).exists():
            # AMR isolates: E. coli mostly cipro-resistant, S. aureus mixed.
            lab = [
                ("E. coli", "Ciprofloxacin", "resistant", "abnormal", gastro),
                ("E. coli", "Ciprofloxacin", "resistant", "abnormal", gastro),
                ("E. coli", "Ciprofloxacin", "susceptible", "normal", gastro),
                ("E. coli", "Ceftriaxone", "susceptible", "normal", gastro),
                ("S. aureus", "Amoxicillin", "resistant", "abnormal", None),
                ("S. aureus", "Amoxicillin", "susceptible", "normal", None),
                ("S. aureus", "Ceftriaxone", "intermediate", "abnormal", None),
                ("K. pneumoniae", "Ciprofloxacin", "resistant", "critical", None),
            ]
            for i, (org, abx, sus, flag, dis) in enumerate(lab):
                LabResult.all_objects.create(
                    tenant=tenant, reporter=doctor, lab_test=rapid_strep,
                    disease=dis, organism=org, antibiotic=abx, susceptibility=sus,
                    flag=flag, value="culture + AST", patient_age_group="19-40",
                    patient_sex="M" if i % 2 else "F",
                    region=regions[i % len(regions)],
                )
            self.stdout.write(f"lab results: {len(lab)}")

        if not Immunization.all_objects.filter(tenant=tenant).exists():
            # vaccine, dose, age band, repeat count.
            imm = [
                ("BCG", 1, "0-1", 9), ("OPV", 1, "0-1", 7), ("OPV", 2, "0-1", 5),
                ("Pentavalent", 1, "0-1", 6), ("Measles", 1, "0-5", 8),
                ("Yellow Fever", 1, "0-5", 4), ("Tetanus", 1, "19-40", 3),
            ]
            rows = []
            for i, (vac, dose, age, count) in enumerate(imm):
                rows += [Immunization(
                    tenant=tenant, reporter=nurse, vaccine=vac, dose_number=dose,
                    patient_age_group=age, region=regions[i % len(regions)],
                ) for _ in range(count)]
            Immunization.all_objects.bulk_create(rows)
            self.stdout.write(f"immunizations: {len(rows)}")

        if not VitalEvent.all_objects.filter(tenant=tenant).exists():
            births = [VitalEvent(
                tenant=tenant, reporter=nurse, event_type=VitalEvent.Kind.BIRTH,
                patient_age_group="0-1", region=regions[i % len(regions)],
            ) for i in range(40)]
            VitalEvent.all_objects.bulk_create(births)
            # Deaths incl. maternal + infant, so MMR/IMR are non-zero.
            deaths = [
                (malaria, False, True, "0-1"),   # infant
                (gastro, False, True, "0-1"),    # infant
                (htn, True, False, "19-40"),     # maternal
                (malaria, False, False, "41-60"),
                (dm2, False, False, "60+"),
            ]
            for i, (cause, mat, inf, age) in enumerate(deaths):
                VitalEvent.all_objects.create(
                    tenant=tenant, reporter=doctor, event_type=VitalEvent.Kind.DEATH,
                    cause=cause, maternal_death=mat, infant_death=inf,
                    patient_age_group=age, region=regions[i % len(regions)],
                )
            self.stdout.write(f"vital events: {len(births)} births + {len(deaths)} deaths")

        if not StockReport.all_objects.filter(tenant=tenant).exists():
            stock = [
                (amox, 320, 180, False), (paracetamol, 0, 240, True),
                (artemether, 45, 210, True), (salbutamol, 120, 60, False),
                (metformin, 200, 90, False), (lisinopril, 15, 110, True),
            ]
            for i, (med, on_hand, consumed, short) in enumerate(stock):
                StockReport.all_objects.create(
                    tenant=tenant, reporter=User.objects.get(username=Role.PHARMACIST.value),
                    medication=med, on_hand=on_hand, consumed=consumed,
                    shortage=short, region=regions[i % len(regions)],
                )
            self.stdout.write(f"stock reports: {len(stock)}")

        from apps.analytics.models import (
            Appointment, CommunityHealthReport, FacilityMetric, InsuranceClaim,
        )
        pharmacist = User.objects.get(username=Role.PHARMACIST.value)

        if not CommunityHealthReport.all_objects.filter(tenant=tenant).exists():
            chw = [
                ("pregnancy", False, True, "19-40", 6),
                ("newborn", False, False, "0-1", 5),
                ("malnutrition", True, True, "0-5", 4),
                ("death", True, True, "60+", 2),
                ("other", False, False, "19-40", 3),
            ]
            rows = []
            for i, (kind, danger, ref, age, count) in enumerate(chw):
                rows += [CommunityHealthReport(
                    tenant=tenant, reporter=nurse, report_type=kind,
                    danger_signs=danger, referred=ref, patient_age_group=age,
                    region=regions[i % len(regions)],
                ) for _ in range(count)]
            CommunityHealthReport.all_objects.bulk_create(rows)
            self.stdout.write(f"chw reports: {len(rows)}")

        if not FacilityMetric.all_objects.filter(tenant=tenant).exists():
            # A week of daily snapshots: ~70-85% occupancy, varying wait/throughput.
            fac = [(100, 72, 35, 18, 64), (100, 81, 48, 16, 71), (100, 68, 28, 20, 58),
                   (100, 90, 55, 15, 80), (100, 77, 40, 18, 66), (100, 84, 50, 17, 74),
                   (100, 79, 38, 19, 69)]
            rows = [FacilityMetric(
                tenant=tenant, reporter=doctor, beds_total=bt, beds_occupied=bo,
                avg_wait_minutes=w, staff_on_duty=s, patients_treated=p,
                region=regions[i % len(regions)],
            ) for i, (bt, bo, w, s, p) in enumerate(fac)]
            FacilityMetric.all_objects.bulk_create(rows)
            self.stdout.write(f"facility metrics: {len(rows)}")

        if not InsuranceClaim.all_objects.filter(tenant=tenant).exists():
            claims = [
                (malaria, 15000, "paid"), (flu, 8000, "approved"),
                (htn, 42000, "approved"), (dm2, 55000, "paid"),
                (asthma, 23000, "rejected"), (gastro, 12000, "submitted"),
                (strep, 9000, "paid"), (malaria, 18000, "submitted"),
                (htn, 38000, "rejected"), (dm2, 61000, "approved"),
            ]
            for i, (dis, amt, st) in enumerate(claims):
                InsuranceClaim.all_objects.create(
                    tenant=tenant, reporter=pharmacist, diagnosis=dis, amount=amt,
                    status=st, patient_age_group="19-40",
                    region=regions[i % len(regions)],
                )
            self.stdout.write(f"insurance claims: {len(claims)}")

        if not Appointment.all_objects.filter(tenant=tenant).exists():
            # mode, status, repeat — telemedicine mix + some no-shows.
            appts = [
                ("in_person", "completed", 12), ("in_person", "no_show", 3),
                ("telemedicine", "completed", 8), ("telemedicine", "no_show", 2),
                ("in_person", "scheduled", 5), ("telemedicine", "scheduled", 4),
                ("in_person", "cancelled", 2),
            ]
            rows = []
            for i, (mode, st, count) in enumerate(appts):
                rows += [Appointment(
                    tenant=tenant, reporter=doctor, mode=mode, status=st,
                    reason="Follow-up", region=regions[i % len(regions)],
                ) for _ in range(count)]
            Appointment.all_objects.bulk_create(rows)
            self.stdout.write(f"appointments: {len(rows)}")

        self.stdout.write(self.style.SUCCESS("seed_dev complete."))
