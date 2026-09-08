from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .current import clear_current_tenant, set_current_tenant
from .models import Tenant

_MISS = object()


def _lookup_tenant(request):
    # 1. Explicit header wins (APIs, mobile clients).
    slug = request.headers.get("X-Tenant-ID")
    if slug:
        return Tenant.objects.filter(slug=slug).first()

    host = request.get_host().split(":")[0]
    # 2. Full custom domain match.
    by_domain = Tenant.objects.filter(domain=host).first()
    if by_domain:
        return by_domain

    # 3. Subdomain of BASE_DOMAIN -> slug (e.g. hospital-a.health.com).
    base = settings.BASE_DOMAIN
    if host.endswith("." + base):
        sub = host[: -len("." + base)]
        return Tenant.objects.filter(slug=sub).first()
    return None


def _resolve_tenant(request):
    """The same lookup, cached: it ran a query on every single request.

    Tenant.save() drops the entry, so an edit is seen at once in the worker
    that made it; the short TTL is what the other workers wait out under the
    default per-process cache. A miss and a no-such-tenant are both cached —
    a bad slug hammering the API must not mean a query per hit.
    """
    key = "tenant:" + (request.headers.get("X-Tenant-ID")
                       or "@" + request.get_host().split(":")[0])
    hit = cache.get(key, _MISS)
    if hit is _MISS:
        hit = _lookup_tenant(request)
        cache.set(key, hit, 30)
    return hit


# Routes a pending/rejected tenant may still hit (so its admin can log in and
# see the status). Prefix match.
_SUBSCRIPTION_GATE_ALLOW = (
    "/api/auth/token/",
    # The signup picker: it lists the organizations you may join, so a
    # stale slug from the last user must not block reading it.
    "/api/auth/register/organizations/",
    # Forgotten passwords: the same stale slug must not lock someone out
    # of the one flow that gets them back in.
    "/api/auth/password-reset/",
)


def _is_super_admin(request):
    """True when the caller's JWT belongs to a platform super-admin.

    Only consulted on a request the subscription gate is about to block, so
    the extra token decode never touches ordinary traffic. Middleware runs
    before DRF authenticates, hence the manual decode.
    """
    try:
        auth = JWTAuthentication().authenticate(request)
    except AuthenticationFailed:
        return False
    return auth is not None and auth[0].is_super_admin


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = _resolve_tenant(request)
        # Block tenants whose subscription isn't approved yet.
        allowed = request.path.startswith(_SUBSCRIPTION_GATE_ALLOW)
        # A super-admin reaches every organization, approved or not: they are
        # the one who approves it, and a pending tenant they cannot open is a
        # tenant they cannot review.
        if (tenant and not allowed
                and tenant.subscription_status != Tenant.SubscriptionStatus.APPROVED
                and not _is_super_admin(request)):
            return JsonResponse(
                {"success": False,
                 "message": "This organization's subscription is awaiting approval."},
                status=403,
            )
        request.tenant = tenant
        set_current_tenant(tenant)
        try:
            return self.get_response(request)
        finally:
            clear_current_tenant()
