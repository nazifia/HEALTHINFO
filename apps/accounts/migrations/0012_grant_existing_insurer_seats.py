from django.db import migrations

# Answering claims and keeping the tariff used to come with the insurer role.
# They are grants now, so every unflagged insurer seat already on a desk keeps
# what it had; its admin takes a grant back from there. Admin seats hold the
# whole catalog implicitly and need nothing written.
GRANTS = ["decide_claims", "edit_tariff"]


def grant(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(role="hmo", is_admin=False):
        user.privileges = sorted(set(user.privileges or []) | set(GRANTS))
        user.save(update_fields=["privileges"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_unseat_national_government")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
