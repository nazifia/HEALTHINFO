"""CORS gated on runtime mode (admin-toggled), not just startup DEBUG.

Dev: reflect any Origin so the Flutter web client on a random localhost port
can call the API. Prod: only the explicit CORS_ALLOWED_ORIGINS. Flip live from
the Django admin (Governance -> Runtime config).
"""
from corsheaders.middleware import CorsMiddleware


class ModeAwareCorsMiddleware(CorsMiddleware):
    def check_signal(self, request):
        from apps.governance.models import is_prod

        if not is_prod():
            return True  # dev: any origin allowed (reflected per-request)
        return super().check_signal(request)
