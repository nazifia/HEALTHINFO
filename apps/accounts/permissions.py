from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role

# Roles allowed to create/edit content. Public + nurse are read-mostly here;
# nurse contribution would go through the (future) draft workflow, not direct write.
WRITE_ROLES = {Role.SUPER_ADMIN, Role.TENANT_ADMIN, Role.DOCTOR, Role.PHARMACIST}

# Roles allowed to file case reports. Includes nurses — reporting cases is core
# clinical work — unlike catalog authoring which stays in WRITE_ROLES.
REPORT_ROLES = WRITE_ROLES | {Role.NURSE}


class IsTenantMember(BasePermission):
    """User must belong to the request's tenant (or be super-admin)."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_super_admin:
            return True
        return request.tenant is not None and user.tenant_id == request.tenant.id


class IsSuperAdmin(BasePermission):
    """Platform-wide super admin only (no tenant scope)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_super_admin


class ReadOnlyOrWriteRole(BasePermission):
    """Anyone in the tenant reads; only WRITE_ROLES mutate.

    Global reference rows (tenant=NULL, shared across all tenants) are read-only
    to tenant users — only super-admins may edit them, so one tenant can't alter
    shared data for everyone.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role in WRITE_ROLES

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if getattr(obj, "tenant_id", None) is None:
            return request.user.is_super_admin
        return True


class ReadOnlyOrReportRole(BasePermission):
    """Anyone in the tenant reads; only REPORT_ROLES (clinical staff) file reports.

    Super-admins write too — they pass IsTenantMember on any tenant and may not
    carry a clinical role, so gate on is_super_admin like that permission does.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_super_admin or user.role in REPORT_ROLES
