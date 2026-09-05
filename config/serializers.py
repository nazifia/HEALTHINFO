"""Naming for the related rows an API answer points at.

A bare pk on screen answers nothing: "patient 41" names no one. Serializers
that resolve a relation by hand (``patient_name = CharField(source=...)``)
already read well; this mixin covers the rest so no client has to render an id
where a name belongs.
"""
from rest_framework import serializers


class NamedRelationsMixin:
    """Adds ``<field>_name`` (``<field>_names`` for a to-many) to the output.

    The value is the related row's own ``__str__`` — the same text Django's
    admin shows — so a model decides once how it is named and every list,
    detail page and export follows. A relation the serializer already resolves
    keeps its own field: an explicit one always wins.

    ponytail: one ``str()`` per relation per row, so a list of 25 rows costs a
    query per relation unless the view's queryset already selects it. Add
    ``select_related``/``prefetch_related`` to that view if a list drags.
    """

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for name, field in self.fields.items():
            many = isinstance(field, serializers.ManyRelatedField)
            relation = field.child_relation if many else field
            if not isinstance(relation, serializers.PrimaryKeyRelatedField):
                continue
            key = f"{name}_names" if many else f"{name}_name"
            # Nothing to name: no pk in the answer, or a name already there.
            if key in data or not data.get(name):
                continue
            related = self._related(instance, field)
            if related is None:
                continue
            data[key] = (
                [str(row) for row in related.all()] if many else str(related)
            )
        return data

    @staticmethod
    def _related(instance, field):
        """The related object(s) behind `field`, walking its source path."""
        obj = instance
        for attr in field.source_attrs:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
        return obj
