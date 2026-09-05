from django.db import migrations, models


def mark_immediate(apps, schema_editor):
    """Flag the epidemic-prone diseases the standard seed already ships.

    Keyed on slug, so a tenant that renamed a disease keeps its flag and one
    that never seeded gets nothing.
    """
    Disease = apps.get_model("catalog", "Disease")
    Disease.objects.filter(
        slug__in=["cholera", "measles", "bacterial-meningitis", "covid-19"]
    ).update(notifiable=True, notify_immediately=True)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_alter_article_tenant_alter_disease_tenant_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='disease',
            name='notify_immediately',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_immediate, migrations.RunPython.noop),
    ]
