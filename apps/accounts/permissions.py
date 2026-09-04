from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import LICENSED_ROLES, Role

# Roles allowed to create/edit content. Public + nurse are read-mostly here;
# nurse contribution would go through the (future) draft workflow, not direct write.
WRITE_ROLES = {Role.SUPER_ADMIN, Role.TENANT_ADMIN, Role.DOCTOR, Role.PHARMACIST}

# Roles allowed to file case reports. Includes the nursing cadres (nurse,
# midwife, CHEW) — reporting cases is core clinical work — unlike catalog
# authoring which stays in WRITE_ROLES.
REPORT_ROLES = WRITE_ROLES | {Role.NURSE, Role.MIDWIFE, Role.CHEW}


def sees_whole_tenant(user):
    """True when this user reads their tenant's records in full.

    Clinicians — the licensed cadres — are narrowed to their own patients and
    the records they filed themselves: a doctor at a hospital has no business
    listing the whole registry. Everyone else keeps the full tenant view,
    because their job needs it: a pharmacist dispenses scripts other people
    wrote, and a tenant admin has to be able to audit the lot.

    Tenant scoping still runs underneath this. It only ever narrows a tenant's
    own rows, it never widens them to another tenant's.
    """
    return not (user.is_authenticated and user.role in LICENSED_ROLES)


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


class IsClinicalStaff(BasePermission):
    """Clinical staff only — reads included.

    Unlike ReadOnlyOrReportRole, this does not open reads to every tenant
    member: it guards identifying patient data, where listing is as sensitive
    as writing. Pair with IsTenantMember for the tenant check.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_super_admin or user.role in REPORT_ROLES


class IsTenantAdmin(BasePermission):
    """Tenant admin (or super admin) — for tenant-governance reads like the
    patient access log, which clinical staff generate but must not audit."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_super_admin or user.role == Role.TENANT_ADMIN


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


# The pharmacy module has two seats. Its admin — the tenant's admin, or a super
# admin — sets prices, corrects stock and decides claims; its staff (the
# pharmacists) receive consignments, dispense and take payment. The split is by
# consequence: anything that rewrites what money is owed is the admin's.
PHARMACY_ADMIN_ROLES = {Role.SUPER_ADMIN, Role.TENANT_ADMIN}
PHARMACY_STAFF_ROLES = PHARMACY_ADMIN_ROLES | {Role.PHARMACIST}


def is_pharmacy_admin(user):
    return bool(user.is_authenticated) and (
        user.is_super_admin or user.role in PHARMACY_ADMIN_ROLES
    )


class IsPharmacyStaff(BasePermission):
    """Pharmacy staff or admin — reads included.

    Not open to every tenant member the way report reads are: cost prices,
    margins and a named patient's claims are commercial and clinical data both.
    Pair with IsTenantMember for the tenant check.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_super_admin or user.role in PHARMACY_STAFF_ROLES


class IsPharmacyAdminOrReadOnly(BasePermission):
    """Staff read; only the pharmacy admin writes.

    Guards the reference data a sale prices itself from — the item list, the
    HMOs and their coverage — so a dispensing error can't be papered over by
    editing the price it was charged at.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_pharmacy_admin(request.user)
