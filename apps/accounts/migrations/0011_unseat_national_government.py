"""A health authority answers for a state, never the country.

Government seats sitting on the national tier read every state's rollups —
the platform admin's view. They now fail closed (User.has_patch), so leave
their patch unset: the user list then shows them as needing a jurisdiction,
and the serializer makes the admin pick a state before the seat reads again.
Which state is a human's call, so nothing here guesses one.
"""
from django.db import migrations


def unseat_national(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        role="government", jurisdiction__level="national"
    ).update(jurisdiction=None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_user_privileges"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(unseat_national, migrations.RunPython.noop),
    ]
