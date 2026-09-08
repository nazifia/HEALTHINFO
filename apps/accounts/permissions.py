from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import LICENSED_ROLES, Role

# Roles allowed to create/edit content. Public + nurse are read-mostly here;
# nurse contribution would go through the (future) draft workflow, not direct write.
WRITE_ROLES = {Role.SUPER_ADMIN, Role.TENANT_ADMIN, Role.DOCTOR, Role.PHARMACIST}

# Roles allowed to file case reports. Includes the nursing cadres (nurse,
# midwife, CHEW) — reporting cases is core clinical work — unlike catalog
# authoring which stays in WRITE_ROLES.
REPORT_ROLES = WRITE_ROLES | {Role.NURSE, Role.MIDWIFE, Role.CHEW}

# The patient's own seat. They read their record through /api/portal/, which
# answers for them and nobody else; the report registers are staff screens and
# every row on one belongs to some other patient.
PATIENT_ROLES = {Role.PUBLIC}

# Seats sitting inside a tenant that are not its staff. An insurer reads the
# claims raised against its own scheme and nothing else in there, so the tenant
# gate below is default-deny for them: a view has to say ``insurer_ok = True``
# before an insurer reaches it, and a new endpoint is closed until it does.
INSURER_ROLES = {Role.HMO}

# Seats with no tenant at all: a health authority reads the cross-tenant
# rollups (aggregates, never a named patient) and nothing tenant-scoped.
OVERSIGHT_ROLES = {Role.GOVERNMENT}


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
        if user.role in INSURER_ROLES and not getattr(view, "insurer_ok", False):
            return False
        return request.tenant is not None and user.tenant_id == request.tenant.id


class IsSuperAdmin(BasePermission):
    """Platform-wide super admin only (no tenant scope)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_super_admin


class IsPlatformAdmin(IsSuperAdmin):
    """Super admin working platform-wide — refused while inside one tenant.

    A super admin who opens a clinic or a pharmacy (the request carries that
    tenant) is working as that organization, so the cross-tenant rollups stay
    shut until they leave it: what they read on screen is that tenant's data
    and nothing else. Leaving the organization drops the tenant from the
    request and the platform views answer again.
    """

    def has_permission(self, request, view):
        return (super().has_permission(request, view)
                and getattr(request, "tenant", None) is None)


class IsPlatformReader(BasePermission):
    """Cross-tenant aggregate reads: the platform admin, or a government seat.

    Refused inside a tenant for the same reason IsPlatformAdmin is — what you
    read there is that one organization's data. Everything behind this
    permission is a rollup, so a health authority reading it never sees a named
    patient, and it is read-only by construction (all GET views).

    A health authority is also refused without a jurisdiction set. Its rollups
    narrow to the patch it answers for, so a seat with none has no patch —
    refusing is the fail-closed half of that narrowing, and mirrors an insurer
    with no scheme.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or getattr(request, "tenant", None) is not None:
            return False
        if user.is_super_admin:
            return True
        return user.role in OVERSIGHT_ROLES and user.jurisdiction_id is not None


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


class IsTenantAdminOrReadOnly(BasePermission):
    """Anyone in the tenant reads; only the tenant admin writes.

    For rosters and the like: staff need to see who is on, but who is on is
    the admin's to set. Pair with IsTenantMember for the tenant check.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
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
        user = request.user
        if not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            # Listing a register is reading other people's records, so the
            # patient seat is not "anyone in the tenant" here: theirs comes
            # back from /api/portal/history/, filtered to them.
            return user.is_super_admin or user.role not in PATIENT_ROLES
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


class IsPharmacyStaffOrInsurerReadOnly(IsPharmacyStaff):
    """Pharmacy staff as usual; the insurer seat reads and never writes.

    The insurer answers a claim through its own transitions elsewhere — nothing
    here lets them edit the pharmacy's record of what was dispensed.
    """

    def has_permission(self, request, view):
        user = request.user
        if user.is_authenticated and user.role in INSURER_ROLES:
            return request.method in SAFE_METHODS
        return super().has_permission(request, view)


class IsPharmacyStaffOrInsurer(IsPharmacyStaff):
    """Pharmacy staff as usual; the insurer seat on the same footing.

    Only for a view whose queryset is already narrowed to the caller's own
    records — a notification is addressed to one person, so that scoping is
    the fence and this settles nothing but whether the seat is admitted.
    """

    def has_permission(self, request, view):
        user = request.user
        if user.is_authenticated and user.role in INSURER_ROLES:
            return True
        return super().has_permission(request, view)


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


class IsSchemePriceListEditor(BasePermission):
    """A scheme's price list: its own insurer writes it, pharmacy staff read.

    The rows say what a contract pays, so the party that agreed the contract
    keeps them — an insurer editing its own scheme, or the pharmacy admin for
    a scheme with no seat of its own. A pharmacist reads and never writes: a
    dispensing error must not be fixable by moving what the cover was.

    Pair with ``insurer_scope`` on the queryset; this only settles who writes,
    ``has_object_permission`` settles that an insurer writes its scheme alone.
    """

    def _may_write(self, user, hmo_id=None):
        if not user.is_authenticated:
            return False
        if user.role in INSURER_ROLES:
            # A seat with no scheme has no list of its own to keep.
            return user.hmo_id is not None and hmo_id in (None, user.hmo_id)
        return is_pharmacy_admin(user)

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return (user.is_super_admin or user.role in PHARMACY_STAFF_ROLES
                    or user.role in INSURER_ROLES)
        return self._may_write(user)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return self._may_write(request.user, obj.hmo_id)
