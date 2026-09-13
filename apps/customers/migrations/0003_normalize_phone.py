"""Fold old customer numbers onto the one shape lookups match.

``Customer.save`` normalizes ``phone`` now (see the model), but customers keyed
before that kept whatever the counter typed, and the by-number lookup and
``?search=`` match on digits. Two spellings of one number that both exist here
are two rows the unique constraint already allows; the second keeps its old
spelling rather than fail the migration, and stays findable by digits.
"""
from django.db import migrations

from apps.accounts.models import normalize_phone


def normalize(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    for pk, tenant_id, phone in Customer.objects.values_list("pk", "tenant_id", "phone"):
        fixed = normalize_phone(phone)
        if fixed == phone or Customer.objects.filter(
            tenant_id=tenant_id, phone=fixed
        ).exists():
            continue
        Customer.objects.filter(pk=pk).update(phone=fixed)


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0002_initial"),
    ]

    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
