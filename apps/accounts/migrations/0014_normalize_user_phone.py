"""Fold existing user phones onto the one shape sign-in matches.

``User.save`` normalizes ``phone`` now (see the model), but rows minted before
that kept whatever the admin typed — "+2348031234567" — while the login screen
folds what the person types to "08031234567", so those seats could never sign
in. Two spellings of one number that both exist are two rows the unique
constraint already allows; the second keeps its old spelling rather than fail
the migration.
"""
from django.db import migrations

from apps.accounts.models import normalize_phone


def normalize(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for pk, phone in User.objects.values_list("pk", "phone"):
        fixed = normalize_phone(phone)
        if fixed == phone or User.objects.filter(phone=fixed).exists():
            continue
        User.objects.filter(pk=pk).update(phone=fixed)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_user_terms_accepted_at"),
    ]

    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
