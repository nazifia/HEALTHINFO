from django.conf import settings

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


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = _resolve_tenant(request)
        request.tenant = tenant
        set_current_tenant(tenant)
        try:
            return self.get_response(request)
        finally:
            clear_current_tenant()
