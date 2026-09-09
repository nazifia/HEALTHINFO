"""Rewrite regions saved under the Flutter picker's old spellings.

Until scripts/gen_nigeria.py made one list the source, the mobile picker and the
server's Jurisdiction tree were maintained by hand and had drifted: the picker
offered "Gayuk, Adamawa" and "Bwari, FCT - Abuja" for a validator that only
accepted "Guyuk, Adamawa" and "Bwari, Federal Capital Territory". Reports filed
before the lists were merged hold the picker's spelling, so re-saving one now
fails validation and the by-state rollups split the FCT in two.

Every rewrite below is a spelling of the same place — no report changes which
local government it belongs to.

Not reversible: the old spellings are exactly what the serializer rejects, so
putting them back would leave rows that cannot be saved. Rolling this migration
back leaves the corrected values, which every version of the code accepts.
"""
from django.db import migrations

# Old "LGA, State" -> the spelling on the canonical INEC list. The state rename
# accounts for the six FCT entries; the rest are one local government each.
RENAMES = {
    "Abaji, FCT - Abuja": "Abaji, Federal Capital Territory",
    "Abuja Municipal, FCT - Abuja": "Municipal Area Council, Federal Capital Territory",
    "Bwari, FCT - Abuja": "Bwari, Federal Capital Territory",
    "Gwagwalada, FCT - Abuja": "Gwagwalada, Federal Capital Territory",
    "Kuje, FCT - Abuja": "Kuje, Federal Capital Territory",
    "Kwali, FCT - Abuja": "Kwali, Federal Capital Territory",
    "Ado Ekiti, Ekiti": "Ado-Ekiti, Ekiti",
    "Ardo Kola, Taraba": "Ardo-Kola, Taraba",
    "Atakunmosa East, Osun": "Atakumosa East, Osun",
    "Atakunmosa West, Osun": "Atakumosa West, Osun",
    "Dutsin Ma, Katsina": "Dutsin-Ma, Katsina",
    "Gayuk, Adamawa": "Guyuk, Adamawa",
    "Ido Osi, Ekiti": "Ido-Osi, Ekiti",
    "Ikpoba Okha, Edo": "Ikpoba-Okha, Edo",
    "Onuimo, Imo": "Unuimo, Imo",
    # seed_dev and simulate wrote this one, which neither list ever accepted.
    "Bwari, FCT": "Bwari, Federal Capital Territory",
}

# Every model carrying a "LGA, State" region, as (app label, model name).
REGION_MODELS = [
    ("analytics", "CaseReport"),
    ("analytics", "AdverseDrugReaction"),
    ("analytics", "LabResult"),
    ("analytics", "Immunization"),
    ("analytics", "VitalEvent"),
    ("analytics", "StockReport"),
    ("analytics", "CommunityHealthReport"),
    ("analytics", "FacilityMetric"),
    ("analytics", "InsuranceClaim"),
    ("analytics", "Appointment"),
    ("analytics", "Prescription"),
    ("analytics", "Consultation"),
    ("patients", "Patient"),
]


def canonicalise(apps, schema_editor):
    for app_label, model_name in REGION_MODELS:
        model = apps.get_model(app_label, model_name)
        # _base_manager, not objects: these models are tenant-scoped, and a
        # migration runs with no tenant bound, so the default manager would
        # match nothing and quietly rewrite none of them.
        rows = model._base_manager
        for old, new in RENAMES.items():
            rows.filter(region=old).update(region=new)


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0017_remove_aiinteraction_feedback"),
        ("patients", "0008_patient_user"),
    ]

    operations = [
        migrations.RunPython(canonicalise, migrations.RunPython.noop),
    ]
