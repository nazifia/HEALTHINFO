"""OPTIONS metadata that names the rows a relation can point at.

DRF deliberately leaves ``choices`` off relational fields, so a form generated
from OPTIONS has nothing to offer for a foreign key but a box to type a raw id
into — and nobody knows a supplier, a scheme or a stock item by its id.

Every writable relation here reads through its own field queryset, which for a
tenant-owned model is the tenant-scoped default manager, so listing the rows
adds no access a GET of the same list would not already give.

ponytail: one extra query per writable relation per OPTIONS call, and lists
longer than MAX_RELATED_CHOICES are left for the client's own type-ahead. Move
to a search endpoint per relation if a form ever needs a longer list than this.
"""
from django.utils.encoding import force_str
from rest_framework import serializers
from rest_framework.metadata import SimpleMetadata

# Longest related list still worth sending whole. Past this a dropdown is not a
# picker either, and the client searches the relation's own endpoint instead.
MAX_RELATED_CHOICES = 500


class RelatedChoicesMetadata(SimpleMetadata):
    def get_field_info(self, field):
        info = super().get_field_info(field)
        many = isinstance(field, serializers.ManyRelatedField)
        relation = field.child_relation if many else field
        if not isinstance(relation, serializers.RelatedField):
            return info
        if info.get("read_only"):
            return info
        # OPTIONS alone can't tell a to-many relation from a to-one; say so, so
        # the client renders a multi-select rather than a comma-separated list.
        if many:
            info["multiple"] = True
        queryset = relation.get_queryset()
        if queryset is None:
            return info
        rows = list(queryset[:MAX_RELATED_CHOICES + 1])
        if len(rows) > MAX_RELATED_CHOICES:
            return info
        choices = [
            {"value": row.pk,
             "display_name": force_str(relation.display_value(row))}
            for row in rows
        ]
        choices.sort(key=lambda c: c["display_name"].lower())
        info["choices"] = choices
        return info
