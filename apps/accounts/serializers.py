from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.tenants.models import Jurisdiction, Tenant

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    # Write-only password: set on create, optional rotation on update. Tenant is
    # writable but the view only honours it for super-admins (see UserViewSet).
    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "phone", "email", "role", "tenant", "tenant_name",
            "is_active", "password",
        )

    def validate_username(self, value):
        # Store blank as NULL (field is null=True) so empty display names are
        # consistently absent, not "" — the client renders absent as "—".
        return value.strip() or None

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        # role is NOT registrable: a public endpoint that let the caller pick
        # their own role is privilege escalation to super_admin. Forced below.
        fields = ("id", "username", "phone", "email", "password")

    def validate_username(self, value):
        return value.strip() or None

    def create(self, validated_data):
        password = validated_data.pop("password")
        # New users are bound to the request tenant; role is always public.
        request = self.context["request"]
        user = User(tenant=request.tenant, role=Role.PUBLIC, **validated_data)
        user.set_password(password)
        user.save()
        return user


class OnboardingSerializer(serializers.Serializer):
    """Self-serve org signup: create a Tenant + its first tenant_admin user.

    Public endpoint (no tenant context). Tenant and admin are created together
    in one transaction so a failed user never leaves an orphan tenant.
    """

    org_name = serializers.CharField(max_length=200)
    org_slug = serializers.SlugField(max_length=50)
    org_address = serializers.CharField(required=False, allow_blank=True)
    org_contact = serializers.CharField(max_length=120, required=False, allow_blank=True)
    # The tenant's own jurisdiction (usually its local gov). Optional so signup
    # still works offline of the tree; rollup just skips tenants with none.
    jurisdiction = serializers.PrimaryKeyRelatedField(
        queryset=Jurisdiction.objects.all(), required=False, allow_null=True
    )
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_org_slug(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError("This slug is already taken.")
        return value

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("This phone number is already taken.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        tenant = Tenant.objects.create(
            name=validated_data["org_name"],
            slug=validated_data["org_slug"],
            address=validated_data.get("org_address", ""),
            contact=validated_data.get("org_contact", ""),
            jurisdiction=validated_data.get("jurisdiction"),
            subscription_status=Tenant.SubscriptionStatus.PENDING,
        )
        user = User(
            phone=validated_data["phone"],
            email=validated_data.get("email", ""),
            tenant=tenant,
            role=Role.TENANT_ADMIN,
        )
        user.set_password(validated_data["password"])
        user.save()
        self.instance = {"tenant": tenant, "user": user}
        return self.instance

    def to_representation(self, instance):
        tenant, user = instance["tenant"], instance["user"]
        return {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "address": tenant.address,
                "contact": tenant.contact,
                "jurisdiction": tenant.jurisdiction_id,
            },
            "user": {"id": user.id, "phone": user.phone, "role": user.role},
        }
