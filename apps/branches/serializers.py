from rest_framework import serializers

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")
