from django.db import migrations


def align(apps, schema_editor):
    apps.get_model("accounts", "User").objects.filter(
        is_superuser=True
    ).exclude(role="super_admin").update(role="super_admin")


class Migration(migrations.Migration):
    """Existing superusers kept the role createsuperuser left them.

    User.save() aligns new rows; the rows already in the table only get saved
    when someone edits them, and until then they sign in without the platform
    admin's screens.
    """

    dependencies = [("accounts", "0007_user_jurisdiction")]

    operations = [migrations.RunPython(align, migrations.RunPython.noop)]
