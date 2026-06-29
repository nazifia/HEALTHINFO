"""Export seed/content data so it can be loaded into production.

Dumps the apps that hold authored content (tenants, clinical catalog, runtime
config, embeddings) and skips per-user/runtime tables (analytics, accounts,
sessions, auth perms — those are recreated by `migrate` or generated in prod).

Usage:
    python scripts/export_content.py            # -> content.json
    python scripts/export_content.py out.json

Load on production (after `python manage.py migrate`):
    python manage.py loaddata content.json
"""
import os
import sys

import django
from django.core.management import call_command

# ponytail: explicit app list, not "dumpdata all minus excludes" — keeps user
#   data out by construction instead of by remembering to exclude it.
CONTENT = ["tenants", "catalog", "governance.runtimeconfig", "ai"]

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

out = sys.argv[1] if len(sys.argv) > 1 else "content.json"
with open(out, "w", encoding="utf-8") as fh:
    call_command(
        "dumpdata", *CONTENT,
        natural_foreign=True,   # FK by natural key where models define one
        indent=2,
        stdout=fh,
    )
print(f"wrote {out} ({os.path.getsize(out)} bytes)")
