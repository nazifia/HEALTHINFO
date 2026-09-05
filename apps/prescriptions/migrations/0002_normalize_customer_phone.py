"""Fold old counter-script numbers onto the one shape lookups match.

``Prescription.save`` normalizes ``customer_phone`` now (see the model), but
scripts written before that kept whatever reception typed — "0803-123-4567",
"+234 803 123 4567" — and the by-number lookup matches on digits, so a dashed
number was a script the patient could not be handed back.
"""
from django.db import migrations

from apps.accounts.models import normalize_phone


def normalize(apps, schema_editor):
    Prescription = apps.get_model("prescriptions", "Prescription")
    for pk, phone in Prescription.objects.exclude(customer_phone="").values_list(
        "pk", "customer_phone"
    ):
        fixed = normalize_phone(phone)
        if fixed != phone:
            Prescription.objects.filter(pk=pk).update(customer_phone=fixed)


class Migration(migrations.Migration):

    dependencies = [
        ("prescriptions", "0001_initial"),
    ]

    # Irreversible in the only sense that matters: the old spelling is not
    # kept, and nothing reads it — the number itself is unchanged.
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
