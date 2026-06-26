from django.conf import settings
from django.http import JsonResponse

from .current import clear_current_tenant, set_current_tenant
from .models import Tenant


def _resolve_tenant(request):
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


# Routes a pending/rejected tenant may still hit (so its admin can log in and
# see the status). Prefix match.
_SUBSCRIPTION_GATE_ALLOW = ("/api/auth/token/",)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = _resolve_tenant(request)
        # Block tenants whose subscription isn't approved yet. Admin/super-admin
        # traffic resolves no tenant (bare host), so it's unaffected.
        allowed = request.path.startswith(_SUBSCRIPTION_GATE_ALLOW)
        if (tenant and not allowed
                and tenant.subscription_status != Tenant.SubscriptionStatus.APPROVED):
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
