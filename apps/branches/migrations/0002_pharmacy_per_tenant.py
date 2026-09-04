"""Give every tenant that predates the rule its main branch.

New tenants get one on creation (see apps.branches.models). Tenants already in
the database — hospitals especially, which never had a shop of their own — have
nowhere to dispense from until this runs.
"""
from django.db import migrations


def create_pharmacies(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Branch = apps.get_model("branches", "Branch")
    for tenant in Tenant.objects.all():
        if Branch.objects.filter(tenant=tenant, is_main=True).exists():
            continue
        name = tenant.name
        if tenant.kind == "hospital":
            name = f"{tenant.name} Pharmacy"[:200]
        if Branch.objects.filter(tenant=tenant, name=name).exists():
            continue
        Branch.objects.create(
            tenant=tenant, name=name, address=tenant.address, is_main=True
        )


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0001_initial"),
        ("tenants", "0006_tenant_kind"),
    ]

    # Reverse is a no-op: branches created here may since have taken stock and
    # sales, and dropping them on a rollback would take that with them.
    operations = [migrations.RunPython(create_pharmacies, migrations.RunPython.noop)]
