"""Embed all published content for every tenant.

ponytail: synchronous full reindex. Fine for thousands of rows; move to a
Celery task (per-object on save + nightly sweep) when the corpus or API
latency makes this too slow to run inline.
"""
from django.core.management.base import BaseCommand

from apps.ai.indexing import index_object
from apps.catalog.models import Disease, Medication, Symptom
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Build/refresh embeddings for published content across all tenants."

    def handle(self, *args, **options):
        total = 0
        for tenant in Tenant.objects.all():
            set_current_tenant(tenant)
            try:
                qs = list(Disease.objects.filter(status="published"))
                qs += list(Medication.objects.filter(status="published"))
                qs += list(Symptom.objects.all())  # symptoms have no workflow
                for obj in qs:
                    index_object(obj)
                    total += 1
            finally:
                clear_current_tenant()
        self.stdout.write(self.style.SUCCESS(f"Indexed {total} objects."))
