"""GIN full-text indexes for SearchView (Postgres only).

ponytail: raw expression GIN indexes instead of a SearchVectorField column —
no schema change to the models, so the sqlite/mysql fallback keeps working and
this migration no-ops there. The index expression mirrors what Django's
SearchVector(..., config="english") emits: to_tsvector('english',
COALESCE(col::text, '') || ' ' || ...). Pinned config in apps/catalog/views.py
must stay in sync or the planner falls back to a seq scan (correct, just slow).

Verify on real Postgres with: EXPLAIN ANALYZE on /api/search/ — look for a
Bitmap Index Scan on these indexes. If it shows a Seq Scan, the expression
drifted; upgrade path is a stored SearchVectorField + trigger.
"""
from django.db import migrations

# (index name, table, columns) — columns must match the SearchView vectors.
_INDEXES = [
    ("catalog_disease_fts", "catalog_disease", ["name", "description", "causes", "treatment"]),
    ("catalog_medication_fts", "catalog_medication", ["generic_name", "brand_name", "description", "indications"]),
    ("catalog_procedure_fts", "catalog_procedure", ["name", "description", "indications"]),
    ("catalog_labtest_fts", "catalog_labtest", ["name", "description", "purpose"]),
    ("catalog_article_fts", "catalog_article", ["title", "summary", "body"]),
]


def _expr(columns):
    return " || ' ' || ".join(f"COALESCE({c}::text, '')" for c in columns)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, table, columns in _INDEXES:
        schema_editor.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {table} "
            f"USING gin (to_tsvector('english', {_expr(columns)}))"
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _table, _columns in _INDEXES:
        schema_editor.execute(f"DROP INDEX IF EXISTS {name}")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]
    operations = [migrations.RunPython(create_indexes, drop_indexes)]
