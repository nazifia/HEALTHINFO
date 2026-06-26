"""Per-request current-tenant binding.

ponytail: thread-local holds the active tenant. Ceiling: assumes one tenant
per thread per request (true for sync WSGI/gunicorn). Move to contextvars if
you go async (ASGI) so it survives await boundaries.
"""
import threading

_state = threading.local()


def set_current_tenant(tenant):
    _state.tenant = tenant


def get_current_tenant():
    return getattr(_state, "tenant", None)


def clear_current_tenant():
    _state.tenant = None
