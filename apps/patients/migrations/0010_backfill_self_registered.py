"""Give every self-signed-up account that predates signup creating a patient
record one of its own, the way RegisterSerializer now does.

Accounts already linked to a record (staff linked them) are skipped, so no
one ends up with two. Patient.save() is not available on the historical
model, so the hospital number rule is repeated here: the phone when this
tenant has not given it out, else a generated one.
"""
import secrets

from django.db import migrations


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Patient = apps.get_model("patients", "Patient")
    accounts = User.objects.filter(
        role="public", tenant__isnull=False, patient_record__isnull=True
    )
    for user in accounts.iterator():
        number = user.phone
        if Patient.all_objects.filter(tenant_id=user.tenant_id,
                                  hospital_number=number).exists():
            number = ""
            for _ in range(10):
                candidate = f"0{secrets.randbelow(10 ** 9):09d}"
                if not Patient.all_objects.filter(hospital_number=candidate).exists():
                    number = candidate
                    break
            else:
                raise ValueError("Could not generate a free hospital number")
        Patient.all_objects.create(
            tenant_id=user.tenant_id, user=user, registered_by=user,
            phone=user.phone, hospital_number=number,
            first_name=user.first_name or user.username or user.phone,
            last_name=user.last_name, status="active",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0009_shared_register"),
        ("accounts", "0015_user_role_receptionist"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
