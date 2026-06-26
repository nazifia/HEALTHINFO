"""Standard medical reference data. Idempotent: re-runnable, get_or_create.

    python manage.py seed_standard                 # into 'demo' tenant
    python manage.py seed_standard --tenant my-org  # into another tenant

Loads a real, published catalog — common diseases with genuine ICD-10 codes,
WHO Essential Medicines, clinically significant drug interactions, symptoms,
specialties, and a few labs/procedures/articles. Everything is PUBLISHED so it
shows in the app immediately, and is normal DB content — edit it live via the
app like any other row.

ponytail: flat data tables + create loop. No CSV/fixture loader, no external
source — the dataset is small and curated. Add a loader only if the list grows
past what's comfortable to read here.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import (
    Article, Disease, DrugInteraction, LabTest, Medication, Procedure,
    Specialty, Status, Symptom,
)
from apps.tenants.models import Tenant

# name -> severity (1 mild .. 5 severe)
SYMPTOMS = {
    "Fever": 3, "Cough": 2, "Headache": 2, "Sore throat": 2, "Fatigue": 1,
    "Shortness of breath": 4, "Chest pain": 4, "Nausea": 2, "Vomiting": 3,
    "Diarrhea": 2, "Rash": 2, "Dizziness": 2, "Muscle aches": 2, "Runny nose": 1,
    "Abdominal pain": 3, "Weight loss": 2, "Night sweats": 2, "Joint pain": 2,
    "Blurred vision": 3, "Frequent urination": 2, "Excessive thirst": 2,
    "Palpitations": 3, "Swelling (edema)": 3, "Confusion": 4, "Seizure": 5,
    "Jaundice": 4, "Wheezing": 3, "Loss of appetite": 1, "Chills": 2,
    "Neck stiffness": 4,
}

# generic, brand, class, indications, dosage
MEDS = [
    ("Amoxicillin", "Amoxil", "Penicillin antibiotic", "Bacterial infections (respiratory, ENT, UTI).", "500 mg PO TID"),
    ("Azithromycin", "Zithromax", "Macrolide antibiotic", "Respiratory and atypical infections.", "500 mg day 1, then 250 mg daily x4"),
    ("Ciprofloxacin", "Cipro", "Fluoroquinolone antibiotic", "UTI, GI and systemic gram-negative infections.", "500 mg PO BID"),
    ("Ceftriaxone", "Rocephin", "Third-generation cephalosporin", "Severe bacterial infections, meningitis, typhoid.", "1-2 g IV/IM daily"),
    ("Metronidazole", "Flagyl", "Nitroimidazole antimicrobial", "Anaerobic and protozoal infections.", "400 mg PO TID"),
    ("Paracetamol", "Panadol", "Analgesic / antipyretic", "Pain and fever.", "500-1000 mg PO q6h (max 4 g/day)"),
    ("Ibuprofen", "Advil", "NSAID", "Pain, fever, inflammation.", "400 mg PO q6-8h"),
    ("Aspirin", "Aspirin", "NSAID / antiplatelet", "Antiplatelet in cardiovascular disease; analgesia.", "75-100 mg daily (antiplatelet)"),
    ("Morphine", "MST", "Opioid analgesic", "Moderate to severe pain.", "5-10 mg IV/IM q4h titrated"),
    ("Metformin", "Glucophage", "Biguanide antidiabetic", "First-line type 2 diabetes.", "500-1000 mg PO BID"),
    ("Insulin (regular)", "Actrapid", "Short-acting insulin", "Diabetes mellitus, hyperglycaemic emergencies.", "Subcut, individualised"),
    ("Glibenclamide", "Daonil", "Sulfonylurea", "Type 2 diabetes.", "5 mg PO daily with breakfast"),
    ("Amlodipine", "Norvasc", "Calcium channel blocker", "Hypertension, angina.", "5-10 mg PO daily"),
    ("Lisinopril", "Zestril", "ACE inhibitor", "Hypertension, heart failure.", "10-40 mg PO daily"),
    ("Losartan", "Cozaar", "Angiotensin receptor blocker", "Hypertension, diabetic nephropathy.", "50-100 mg PO daily"),
    ("Hydrochlorothiazide", "Hydrosaluric", "Thiazide diuretic", "Hypertension, oedema.", "12.5-25 mg PO daily"),
    ("Furosemide", "Lasix", "Loop diuretic", "Oedema, heart failure.", "20-80 mg PO/IV daily"),
    ("Atorvastatin", "Lipitor", "HMG-CoA reductase inhibitor (statin)", "Hyperlipidaemia, CVD prevention.", "10-80 mg PO nocte"),
    ("Warfarin", "Coumadin", "Vitamin-K antagonist anticoagulant", "Anticoagulation (AF, VTE, valves).", "Dose to target INR"),
    ("Salbutamol", "Ventolin", "Short-acting beta-2 agonist", "Asthma, COPD bronchospasm.", "100-200 mcg inhaled PRN"),
    ("Beclomethasone", "Becotide", "Inhaled corticosteroid", "Asthma maintenance.", "100-400 mcg inhaled BID"),
    ("Prednisolone", "Deltacortril", "Corticosteroid", "Inflammatory and allergic conditions.", "5-60 mg PO daily, tapered"),
    ("Omeprazole", "Losec", "Proton pump inhibitor", "Peptic ulcer, GORD.", "20-40 mg PO daily"),
    ("Artemether-Lumefantrine", "Coartem", "Antimalarial (ACT)", "Uncomplicated falciparum malaria.", "Weight-based, 3-day course"),
    ("Rifampicin", "Rifadin", "Rifamycin antitubercular", "Tuberculosis (combination).", "10 mg/kg PO daily"),
    ("Isoniazid", "Isovit", "Antitubercular", "Tuberculosis (combination).", "5 mg/kg PO daily"),
    ("Levothyroxine", "Eltroxin", "Thyroid hormone", "Hypothyroidism.", "50-150 mcg PO daily"),
    ("Amitriptyline", "Elavil", "Tricyclic antidepressant", "Depression, neuropathic pain.", "25-75 mg PO nocte"),
    ("Fluoxetine", "Prozac", "SSRI antidepressant", "Depression, anxiety disorders.", "20 mg PO daily"),
    ("Ferrous sulfate", "Feospan", "Oral iron", "Iron-deficiency anaemia.", "200 mg PO BID-TID"),
]

# name, slug, icd10, notifiable, description, treatment, [symptom names], [med generics], [specialty names]
DISEASES = [
    ("Influenza", "influenza", "J10", False,
     "Acute viral respiratory infection caused by influenza viruses.",
     "Rest, fluids, antipyretics; antivirals in high-risk groups.",
     ["Fever", "Cough", "Headache", "Muscle aches", "Runny nose"], ["Paracetamol", "Ibuprofen"], ["Pulmonology"]),
    ("Tuberculosis", "tuberculosis", "A15", True,
     "Chronic bacterial infection by Mycobacterium tuberculosis, usually pulmonary.",
     "Multi-drug regimen (rifampicin, isoniazid and others) for 6 months.",
     ["Cough", "Weight loss", "Night sweats", "Fever", "Fatigue"], ["Rifampicin", "Isoniazid"], ["Pulmonology", "Infectious Disease"]),
    ("Malaria", "malaria", "B54", True,
     "Mosquito-borne Plasmodium infection; falciparum can be fatal.",
     "Artemisinin-based combination therapy; supportive care.",
     ["Fever", "Chills", "Headache", "Muscle aches", "Nausea"], ["Artemether-Lumefantrine", "Paracetamol"], ["Infectious Disease"]),
    ("Type 2 Diabetes", "type-2-diabetes", "E11", False,
     "Insulin resistance causing chronic hyperglycaemia.",
     "Lifestyle change, metformin, escalating therapy; glucose monitoring.",
     ["Fatigue", "Excessive thirst", "Frequent urination", "Blurred vision"], ["Metformin", "Glibenclamide", "Insulin (regular)"], ["Endocrinology"]),
    ("Hypertension", "hypertension", "I10", False,
     "Persistently elevated arterial blood pressure.",
     "Lifestyle change plus ACE inhibitors, ARBs, CCBs or diuretics.",
     ["Headache", "Dizziness", "Chest pain"], ["Amlodipine", "Lisinopril", "Losartan", "Hydrochlorothiazide"], ["Cardiology"]),
    ("Asthma", "asthma", "J45", False,
     "Chronic airway inflammation with reversible obstruction.",
     "Inhaled bronchodilators and corticosteroids; avoid triggers.",
     ["Cough", "Shortness of breath", "Wheezing", "Chest pain"], ["Salbutamol", "Beclomethasone"], ["Pulmonology"]),
    ("Chronic Obstructive Pulmonary Disease", "copd", "J44", False,
     "Progressive airflow limitation, usually from smoking.",
     "Bronchodilators, inhaled steroids, smoking cessation, oxygen.",
     ["Cough", "Shortness of breath", "Wheezing", "Fatigue"], ["Salbutamol", "Beclomethasone", "Prednisolone"], ["Pulmonology"]),
    ("Pneumonia", "pneumonia", "J18", False,
     "Acute infection of the lung parenchyma.",
     "Antibiotics guided by severity; oxygen and fluids as needed.",
     ["Fever", "Cough", "Shortness of breath", "Chest pain", "Chills"], ["Amoxicillin", "Azithromycin", "Ceftriaxone"], ["Pulmonology", "Infectious Disease"]),
    ("Ischaemic Heart Disease", "ischaemic-heart-disease", "I25", False,
     "Reduced coronary blood flow causing angina or infarction.",
     "Antiplatelets, statins, beta-blockers; revascularisation if indicated.",
     ["Chest pain", "Shortness of breath", "Palpitations"], ["Aspirin", "Atorvastatin"], ["Cardiology"]),
    ("Ischaemic Stroke", "ischaemic-stroke", "I63", False,
     "Sudden neurological deficit from cerebral arterial occlusion.",
     "Acute reperfusion where eligible; antiplatelets, risk-factor control.",
     ["Confusion", "Dizziness", "Headache", "Blurred vision"], ["Aspirin", "Atorvastatin"], ["Cardiology"]),
    ("HIV Infection", "hiv-infection", "B20", True,
     "Human immunodeficiency virus causing progressive immune failure.",
     "Lifelong combination antiretroviral therapy; opportunistic-infection care.",
     ["Weight loss", "Fever", "Fatigue", "Night sweats"], [], ["Infectious Disease"]),
    ("Hepatitis B", "hepatitis-b", "B16", True,
     "Viral infection of the liver by hepatitis B virus.",
     "Antivirals in chronic disease; vaccination prevents infection.",
     ["Jaundice", "Fatigue", "Nausea", "Abdominal pain"], [], ["Gastroenterology", "Infectious Disease"]),
    ("Cholera", "cholera", "A00", True,
     "Acute watery diarrhoea from Vibrio cholerae; epidemic-prone.",
     "Aggressive oral/IV rehydration; antibiotics in severe cases.",
     ["Diarrhea", "Vomiting", "Dizziness"], ["Ciprofloxacin"], ["Infectious Disease"]),
    ("Typhoid Fever", "typhoid-fever", "A01.0", True,
     "Systemic infection by Salmonella Typhi.",
     "Appropriate antibiotics; fluids and supportive care.",
     ["Fever", "Abdominal pain", "Headache", "Loss of appetite"], ["Ceftriaxone", "Ciprofloxacin"], ["Infectious Disease"]),
    ("Measles", "measles", "B05", True,
     "Highly contagious viral illness with rash; vaccine-preventable.",
     "Supportive care, vitamin A; manage complications.",
     ["Fever", "Rash", "Cough", "Runny nose"], ["Paracetamol"], ["Infectious Disease"]),
    ("COVID-19", "covid-19", "U07.1", True,
     "Respiratory illness caused by SARS-CoV-2.",
     "Supportive care; oxygen and specific therapies in severe disease.",
     ["Fever", "Cough", "Shortness of breath", "Fatigue", "Loss of appetite"], ["Paracetamol"], ["Pulmonology", "Infectious Disease"]),
    ("Gastroenteritis", "gastroenteritis", "A09", False,
     "Inflammation of the GI tract, usually infectious.",
     "Oral rehydration and supportive care; antibiotics rarely needed.",
     ["Nausea", "Vomiting", "Diarrhea", "Abdominal pain", "Fever"], ["Paracetamol", "Metronidazole"], ["Gastroenterology"]),
    ("Urinary Tract Infection", "urinary-tract-infection", "N39.0", False,
     "Bacterial infection of the urinary tract.",
     "Short-course antibiotics; increase fluids.",
     ["Frequent urination", "Abdominal pain", "Fever"], ["Ciprofloxacin", "Amoxicillin"], ["Nephrology"]),
    ("Iron-Deficiency Anaemia", "iron-deficiency-anaemia", "D50", False,
     "Reduced haemoglobin from inadequate iron stores.",
     "Oral iron and treat the underlying cause.",
     ["Fatigue", "Dizziness", "Shortness of breath"], ["Ferrous sulfate"], ["Hematology"]),
    ("Major Depressive Disorder", "major-depressive-disorder", "F32", False,
     "Persistent low mood and loss of interest impairing function.",
     "Psychotherapy and/or antidepressants.",
     ["Fatigue", "Loss of appetite"], ["Fluoxetine", "Amitriptyline"], ["Psychiatry"]),
    ("Migraine", "migraine", "G43", False,
     "Recurrent moderate-to-severe headache, often with aura.",
     "Acute analgesia/triptans; prophylaxis if frequent.",
     ["Headache", "Nausea", "Blurred vision"], ["Ibuprofen", "Paracetamol"], ["Neurology"]),
    ("Osteoarthritis", "osteoarthritis", "M19", False,
     "Degenerative joint disease with cartilage loss.",
     "Exercise, weight loss, analgesia; joint replacement if severe.",
     ["Joint pain", "Swelling (edema)"], ["Paracetamol", "Ibuprofen"], ["Rheumatology"]),
    ("Chronic Kidney Disease", "chronic-kidney-disease", "N18", False,
     "Progressive, irreversible loss of kidney function.",
     "Control BP and diabetes; manage complications; dialysis if end-stage.",
     ["Fatigue", "Swelling (edema)", "Nausea"], ["Lisinopril", "Furosemide"], ["Nephrology"]),
    ("Hypothyroidism", "hypothyroidism", "E03", False,
     "Underactive thyroid causing metabolic slowing.",
     "Levothyroxine replacement, dose-titrated.",
     ["Fatigue", "Weight loss", "Loss of appetite"], ["Levothyroxine"], ["Endocrinology"]),
    ("Epilepsy", "epilepsy", "G40", False,
     "Recurrent unprovoked seizures from abnormal brain activity.",
     "Antiepileptic drugs; treat the underlying cause where present.",
     ["Seizure", "Confusion", "Dizziness"], [], ["Neurology"]),
    ("Dengue Fever", "dengue-fever", "A90", True,
     "Mosquito-borne viral febrile illness; can progress to severe disease.",
     "Supportive care and careful fluid management; avoid NSAIDs.",
     ["Fever", "Headache", "Muscle aches", "Rash", "Nausea"], ["Paracetamol"], ["Infectious Disease"]),
    ("Bacterial Meningitis", "bacterial-meningitis", "G00", True,
     "Acute infection of the meninges; a medical emergency.",
     "Urgent empirical IV antibiotics; supportive care.",
     ["Fever", "Headache", "Neck stiffness", "Confusion"], ["Ceftriaxone"], ["Neurology", "Infectious Disease"]),
    ("Peptic Ulcer Disease", "peptic-ulcer-disease", "K27", False,
     "Mucosal ulceration of stomach or duodenum.",
     "PPIs, H. pylori eradication; stop NSAIDs.",
     ["Abdominal pain", "Nausea", "Loss of appetite"], ["Omeprazole", "Amoxicillin", "Metronidazole"], ["Gastroenterology"]),
    ("Allergic Rhinitis", "allergic-rhinitis", "J30", False,
     "IgE-mediated nasal inflammation from allergen exposure.",
     "Allergen avoidance, antihistamines, intranasal steroids.",
     ["Runny nose", "Cough"], ["Beclomethasone"], ["Pulmonology"]),
]

# generic_a, generic_b, severity, description, recommendation
INTERACTIONS = [
    ("Warfarin", "Aspirin", "major", "Additive bleeding risk.", "Avoid unless specifically indicated; monitor closely."),
    ("Warfarin", "Ibuprofen", "major", "NSAIDs raise bleeding risk with anticoagulants.", "Avoid; prefer paracetamol."),
    ("Warfarin", "Ciprofloxacin", "major", "Ciprofloxacin potentiates warfarin, raising INR.", "Monitor INR closely; adjust dose."),
    ("Warfarin", "Metronidazole", "major", "Metronidazole inhibits warfarin metabolism.", "Monitor INR; reduce warfarin dose."),
    ("Warfarin", "Rifampicin", "major", "Rifampicin induces metabolism, reducing warfarin effect.", "Expect higher dose need; monitor INR."),
    ("Aspirin", "Ibuprofen", "moderate", "Ibuprofen can block aspirin's antiplatelet effect.", "Separate dosing; review need for both."),
    ("Ibuprofen", "Prednisolone", "moderate", "Additive GI ulceration and bleeding risk.", "Add gastroprotection; limit duration."),
    ("Ibuprofen", "Lisinopril", "moderate", "NSAIDs blunt ACE-inhibitor effect and risk renal impairment.", "Monitor BP and renal function."),
    ("Ibuprofen", "Furosemide", "moderate", "NSAIDs reduce diuretic efficacy and risk renal injury.", "Monitor fluid status and renal function."),
    ("Lisinopril", "Losartan", "moderate", "Dual RAAS blockade risks hyperkalaemia and renal failure.", "Avoid routine combination."),
    ("Lisinopril", "Hydrochlorothiazide", "minor", "Risk of first-dose hypotension.", "Start low; monitor BP."),
    ("Fluoxetine", "Amitriptyline", "major", "Additive serotonergic effect and raised TCA levels.", "Avoid or reduce TCA dose; watch for toxicity."),
    ("Atorvastatin", "Azithromycin", "moderate", "Increased statin exposure and myopathy risk.", "Monitor for muscle symptoms."),
    ("Ciprofloxacin", "Ferrous sulfate", "moderate", "Iron chelates ciprofloxacin, reducing absorption.", "Separate doses by at least 2 hours."),
    ("Prednisolone", "Glibenclamide", "moderate", "Corticosteroids raise blood glucose, opposing hypoglycaemics.", "Monitor glucose; adjust antidiabetic dose."),
]

# name, slug, purpose, normal_range, units, [disease slugs]
LAB_TESTS = [
    ("Full Blood Count", "full-blood-count", "Screen for anaemia, infection and clotting cells.", "Hb 13-17 (M) / 12-15 (F)", "g/dL", ["iron-deficiency-anaemia", "malaria"]),
    ("Fasting Blood Glucose", "fasting-blood-glucose", "Diagnose and monitor diabetes.", "3.9-5.5", "mmol/L", ["type-2-diabetes"]),
    ("HbA1c", "hba1c", "Assess 3-month average glycaemic control.", "<5.7", "%", ["type-2-diabetes"]),
    ("Blood Pressure Measurement", "blood-pressure-measurement", "Assess arterial pressure.", "<120/80", "mmHg", ["hypertension"]),
    ("Sputum AFB Smear", "sputum-afb-smear", "Detect acid-fast bacilli for TB.", "Negative", "", ["tuberculosis"]),
    ("Malaria Rapid Diagnostic Test", "malaria-rdt", "Detect Plasmodium antigen.", "Negative", "", ["malaria"]),
    ("Serum Creatinine", "serum-creatinine", "Assess renal function.", "60-110", "umol/L", ["chronic-kidney-disease"]),
    ("Thyroid Stimulating Hormone", "tsh", "Assess thyroid function.", "0.4-4.0", "mIU/L", ["hypothyroidism"]),
]

# name, slug, description, indications, [disease slugs]
PROCEDURES = [
    ("Chest X-ray", "chest-x-ray", "Plain radiograph of the chest.", "Suspected pneumonia, TB, heart failure.", ["pneumonia", "tuberculosis", "copd"]),
    ("Electrocardiogram", "electrocardiogram", "Records the heart's electrical activity.", "Chest pain, palpitations, arrhythmia.", ["ischaemic-heart-disease", "hypertension"]),
    ("Upper GI Endoscopy", "upper-gi-endoscopy", "Direct visualisation of upper GI tract.", "Suspected peptic ulcer, bleeding, reflux.", ["peptic-ulcer-disease"]),
    ("Lumbar Puncture", "lumbar-puncture", "CSF sampling from the lumbar spine.", "Suspected meningitis or CNS infection.", ["bacterial-meningitis"]),
    ("Spirometry", "spirometry", "Measures lung volumes and airflow.", "Diagnose and grade asthma and COPD.", ["asthma", "copd"]),
]

# title, slug, summary, body, [disease slugs], [med generics]
ARTICLES = [
    ("Understanding Hypertension", "understanding-hypertension",
     "Why blood pressure matters and how it is managed.",
     "Most hypertension is symptomless; regular measurement and adherence to "
     "medication and lifestyle change prevent stroke, heart and kidney disease.",
     ["hypertension"], ["Amlodipine", "Lisinopril"]),
    ("Living with Type 2 Diabetes", "living-with-type-2-diabetes",
     "Daily management, diet and monitoring.",
     "Consistent glucose control through diet, activity and medication prevents "
     "long-term complications affecting eyes, nerves and kidneys.",
     ["type-2-diabetes"], ["Metformin"]),
    ("Recognising an Asthma Attack", "recognising-an-asthma-attack",
     "Warning signs and reliever-inhaler use.",
     "Increasing breathlessness, wheeze and reliever use signal worsening asthma; "
     "seek urgent help when a reliever no longer controls symptoms.",
     ["asthma"], ["Salbutamol"]),
    ("Preventing Malaria", "preventing-malaria",
     "Bite avoidance, prophylaxis and early treatment.",
     "Insecticide-treated nets, indoor spraying and prompt testing of any fever in "
     "endemic areas reduce malaria deaths.",
     ["malaria"], ["Artemether-Lumefantrine"]),
    ("Completing TB Treatment", "completing-tb-treatment",
     "Why the full course matters.",
     "Tuberculosis needs months of combination therapy; stopping early drives drug "
     "resistance and relapse. Directly observed therapy improves cure rates.",
     ["tuberculosis"], ["Rifampicin", "Isoniazid"]),
]


class Command(BaseCommand):
    help = "Seed standard medical reference data (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", default="demo",
            help="Slug of the tenant to load data into (default: demo).",
        )
        parser.add_argument(
            "--global", dest="is_global", action="store_true",
            help="Load as shared global data (tenant=NULL), visible to every tenant.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["is_global"]:
            tenant = None
            self.stdout.write("tenant: <global / all tenants>")
        else:
            slug = opts["tenant"]
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is None:
                raise CommandError(
                    f"No tenant with slug '{slug}'. Create it first (onboarding) "
                    f"or pass --tenant <existing-slug>."
                )
            self.stdout.write(f"tenant: {tenant}")

        def co(model, defaults=None, **lookup):
            """get_or_create scoped to tenant, bypassing the thread-local manager."""
            obj, created = model.all_objects.get_or_create(
                tenant=tenant, defaults=defaults or {}, **lookup
            )
            return obj, created

        symptoms = {}
        for name, sev in SYMPTOMS.items():
            symptoms[name], _ = co(Symptom, {"severity_level": sev}, name=name)
        self.stdout.write(f"symptoms: {len(symptoms)}")

        meds = {}
        for generic, brand, klass, indic, dose in MEDS:
            meds[generic], _ = co(Medication, {
                "brand_name": brand, "drug_class": klass, "indications": indic,
                "dosage": dose, "status": Status.PUBLISHED,
            }, generic_name=generic)
        self.stdout.write(f"medications: {len(meds)}")

        specialties = {}
        diseases = {}
        for (name, dslug, icd, notif, desc, treat, syms, dmeds, specs) in DISEASES:
            d, _ = co(Disease, {
                "name": name, "icd10_code": icd, "notifiable": notif,
                "description": desc, "treatment": treat, "status": Status.PUBLISHED,
            }, slug=dslug)
            d.symptoms.set([symptoms[s] for s in syms])
            d.medications.set([meds[m] for m in dmeds])
            diseases[dslug] = d
            for sp in specs:
                obj, _ = co(Specialty, {"description": f"{sp} specialty."}, name=sp)
                specialties[sp] = obj
                obj.diseases.add(d)
        self.stdout.write(f"diseases: {len(diseases)}  specialties: {len(specialties)}")

        made = 0
        for ga, gb, sev, desc, rec in INTERACTIONS:
            _, created = DrugInteraction.all_objects.get_or_create(
                tenant=tenant, medication_a=meds[ga], medication_b=meds[gb],
                defaults={"severity": sev, "description": desc, "recommendation": rec},
            )
            made += created
        self.stdout.write(f"interactions: +{made} (total target {len(INTERACTIONS)})")

        for name, lslug, purpose, rng, units, dslugs in LAB_TESTS:
            lt, _ = co(LabTest, {
                "name": name, "purpose": purpose, "normal_range": rng,
                "units": units, "status": Status.PUBLISHED,
            }, slug=lslug)
            lt.diseases.set([diseases[d] for d in dslugs])
        self.stdout.write(f"lab tests: {len(LAB_TESTS)}")

        for name, pslug, desc, indic, dslugs in PROCEDURES:
            p, _ = co(Procedure, {
                "name": name, "description": desc, "indications": indic,
                "status": Status.PUBLISHED,
            }, slug=pslug)
            p.diseases.set([diseases[d] for d in dslugs])
        self.stdout.write(f"procedures: {len(PROCEDURES)}")

        for title, aslug, summary, body, dslugs, ameds in ARTICLES:
            a, _ = co(Article, {
                "title": title, "summary": summary, "body": body,
                "status": Status.PUBLISHED,
            }, slug=aslug)
            a.diseases.set([diseases[d] for d in dslugs])
            a.medications.set([meds[m] for m in ameds])
        self.stdout.write(f"articles: {len(ARTICLES)}")

        self.stdout.write(self.style.SUCCESS("seed_standard complete."))
