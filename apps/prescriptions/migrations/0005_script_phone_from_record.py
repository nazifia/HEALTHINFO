"""Give old scripts written against a customer or patient record their number.

``Prescription.save`` copies it on now (see the model): another pharmacy finds
and fills a script on the number alone, and one written against a record with
nothing typed in ``customer_phone`` was unreachable from anywhere else.
"""
from django.db import migrations

from apps.accounts.models import normalize_phone


def backfill(apps, schema_editor):
    Prescription = apps.get_model("prescriptions", "Prescription")
    rows = Prescription.objects.filter(customer_phone="").select_related(
        "customer", "patient"
    )
    for rx in rows:
        for who in (rx.customer, rx.patient):
            phone = normalize_phone(getattr(who, "phone", ""))
            if phone:
                Prescription.objects.filter(pk=rx.pk).update(customer_phone=phone)
                break


class Migration(migrations.Migration):

    dependencies = [
        ("prescriptions", "0004_consultation_band_on_drug_order"),
        ("customers", "0003_normalize_phone"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
