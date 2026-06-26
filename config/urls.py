from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def _empty_sw(request):
    """Silence browser requests for a service worker at the root."""
    return HttpResponse("/* no service worker */", content_type="application/javascript")


def _api_endpoints():
    """Collect every concrete route under /api/ from the URLconf."""
    from django.urls import get_resolver

    routes = []

    def walk(patterns, prefix=""):
        for p in patterns:
            route = prefix + str(p.pattern).lstrip("^").rstrip("$")
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns, route)
            elif (
                route.startswith("api/")
                and route != "api/"
                and "<" not in route  # skip detail routes with path params
                and "(?P" not in route
            ):
                routes.append("/" + route)

    walk(get_resolver().url_patterns)
    return sorted(set(routes))


def _api_index(request):
    return JsonResponse({
        "message": "HEALTH INFO API is working",
        "endpoints": _api_endpoints(),
    })


def _health(request):
    """Liveness/readiness probe: 200 if the DB answers, 503 otherwise.

    Public, unauthenticated, tenant-agnostic — for load balancers and the
    Docker healthcheck. ponytail: one DB round-trip is enough; add Redis/broker
    checks here only if an outage there should fail the probe.
    """
    from django.db import connection

    try:
        connection.ensure_connection()
    except Exception as exc:  # pragma: no cover - exercised via the 503 path
        return JsonResponse({"status": "error", "db": str(exc)}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})


urlpatterns = [
    path("sw.js", _empty_sw),
    path("healthz", _health),
    path("api/health/", _health, name="health"),
    path("", RedirectView.as_view(pattern_name="swagger-ui", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/", _api_index),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.ai.urls")),
    path("api/", include("apps.analytics.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
