"""Classify tenants created before Tenant.kind existed.

Every pre-existing row migrated in as PHARMACY (the default), so hospitals that
signed up earlier are mislabelled. Two ways to fix them:

    manage.py backfill_tenant_kind                        # guess, report only
    manage.py backfill_tenant_kind --apply                # guess, write
    manage.py backfill_tenant_kind gen-hosp --kind hospital --apply

The guess reads the org name. It is a hint, not an authority — that is why it
prints and changes nothing unless --apply is passed.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Tenant

# ponytail: substring match on a lowercased name. A real classifier needs a
# facility register; until one exists the operator reads the dry run.
HOSPITAL_WORDS = (
    "hospital", "clinic", "medical cent", "medical centre", "health cent",
    "infirmary", "teaching hosp", "phc", "primary health",
)


def guess_kind(name):
    lowered = name.lower()
    if any(word in lowered for word in HOSPITAL_WORDS):
        return Tenant.Kind.HOSPITAL
    return Tenant.Kind.PHARMACY


class Command(BaseCommand):
    help = "Set Tenant.kind for tenants that predate the field."

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tenants to set explicitly.")
        parser.add_argument("--kind", choices=[k for k, _ in Tenant.Kind.choices],
                            help="Kind to set on the named slugs.")
        parser.add_argument("--apply", action="store_true",
                            help="Write the changes (default: report only).")

    def handle(self, *args, **options):
        slugs, kind, apply = options["slugs"], options["kind"], options["apply"]
        if slugs and not kind:
            raise CommandError("--kind is required when naming slugs.")
        if kind and not slugs:
            raise CommandError("Name the slugs to set to --kind.")

        if slugs:
            found = Tenant.objects.filter(slug__in=slugs)
            missing = set(slugs) - {t.slug for t in found}
            if missing:
                raise CommandError(f"No tenant with slug: {', '.join(sorted(missing))}")
            changes = [(t, kind) for t in found if t.kind != kind]
        else:
            changes = [(t, guess_kind(t.name)) for t in Tenant.objects.all()]
            changes = [(t, k) for t, k in changes if t.kind != k]

        for tenant, new_kind in changes:
            self.stdout.write(f"{tenant.slug}: {tenant.kind} -> {new_kind}  ({tenant.name})")
        if not changes:
            self.stdout.write("Nothing to change.")
            return
        if not apply:
            self.stdout.write(self.style.WARNING(
                f"{len(changes)} tenant(s) would change. Re-run with --apply to write."))
            return
        for tenant, new_kind in changes:
            tenant.kind = new_kind
            tenant.save(update_fields=["kind", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"{len(changes)} tenant(s) updated."))
