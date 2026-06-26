"""Drop the FTS GIN indexes from 0002 (Postgres only).

SearchView moved from Postgres full-text search to plain icontains, so the
to_tsvector GIN indexes are dead weight (unused, but still cost write
throughput on every insert/update). No-ops on sqlite/mysql, same as 0002.

Reverse re-creates them so 0002 stays meaningful if rolled back.
"""
from django.db import migrations

# Mirror of 0002's _INDEXES (can't import a module whose name starts with a digit).
_INDEXES = [
    ("catalog_disease_fts", "catalog_disease", ["name", "description", "causes", "treatment"]),
    ("catalog_medication_fts", "catalog_medication", ["generic_name", "brand_name", "description", "indications"]),
    ("catalog_procedure_fts", "catalog_procedure", ["name", "description", "indications"]),
    ("catalog_labtest_fts", "catalog_labtest", ["name", "description", "purpose"]),
    ("catalog_article_fts", "catalog_article", ["title", "summary", "body"]),
]


def _expr(columns):
    return " || ' ' || ".join(f"COALESCE({c}::text, '')" for c in columns)


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _table, _columns in _INDEXES:
        schema_editor.execute(f"DROP INDEX IF EXISTS {name}")


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, table, columns in _INDEXES:
        schema_editor.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {table} "
            f"USING gin (to_tsvector('english', {_expr(columns)}))"
        )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_fts_gin_indexes")]
    operations = [migrations.RunPython(drop_indexes, create_indexes)]
