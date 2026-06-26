import django.core.validators
from django.db import migrations, models


def backfill_phone(apps, schema_editor):
    """Give existing rows a unique placeholder phone so the unique/non-null
    constraint can be applied. Real users must update it."""
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(phone__isnull=True):
        user.phone = f"+000000{user.pk:09d}"
        user.save(update_fields=["phone"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # username is no longer the login identifier: optional, non-unique.
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        # 1. add nullable, 2. backfill, 3. lock down to non-null + unique.
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.RunPython(backfill_phone, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.CharField(
                max_length=20,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        regex=r"^\+?\d{7,15}$",
                        message="Enter a valid phone number (7-15 digits, optional leading +).",
                    )
                ],
            ),
        ),
    ]
