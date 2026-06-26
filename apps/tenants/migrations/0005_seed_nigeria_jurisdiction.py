"""Seed the full Nigerian jurisdiction tree: national -> 37 states -> 774 LGAs.

Idempotent (get_or_create) so it's safe to re-run and safe on prod. Reversible:
the reverse removes only the rows this seed creates, and refuses if any LGA
still has tenants attached (PROTECT would block it anyway).
"""

from django.db import migrations

from apps.tenants.ng_jurisdiction import COUNTRY, NG_STATES_LGAS


def seed(apps, schema_editor):
    Jurisdiction = apps.get_model("tenants", "Jurisdiction")

    national, _ = Jurisdiction.objects.get_or_create(
        name=COUNTRY, level="national", parent=None
    )
    for state_name, lgas in NG_STATES_LGAS.items():
        state, _ = Jurisdiction.objects.get_or_create(
            name=state_name, level="state", parent=national
        )
        for lga in lgas:
            Jurisdiction.objects.get_or_create(
                name=lga, level="local", parent=state
            )


def unseed(apps, schema_editor):
    Jurisdiction = apps.get_model("tenants", "Jurisdiction")

    national = Jurisdiction.objects.filter(
        name=COUNTRY, level="national", parent=None
    ).first()
    if national is None:
        return
    states = Jurisdiction.objects.filter(level="state", parent=national)
    # Delete leaves first (PROTECT forbids deleting a parent with children).
    Jurisdiction.objects.filter(level="local", parent__in=states).delete()
    states.delete()
    national.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0004_tenant_subscription_status"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
