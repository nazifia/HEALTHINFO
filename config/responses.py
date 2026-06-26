"""Uniform success/failure message envelopes.

ponytail: failures route through ONE DRF exception handler so every endpoint
reports errors the same way (``success``/``message``/``errors``) without editing
each view. Successes that carry a human message use ``success()``, which merges
the flags into the existing payload rather than nesting it — so the mobile
client and DRF pagination keep reading the same data keys. Data-shaped GETs
(lists, stats) stay raw; they don't need a message.
"""
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def success(message, data=None, status=200):
    """Success envelope. dict data is merged at top level (non-breaking); any
    other value lands under ``data``."""
    payload = {"success": True, "message": message}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    return Response(payload, status=status)


def _first_error(errors):
    """Best human message out of a DRF error dict (first field's first error)."""
    for value in errors.values():
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        if isinstance(value, str):
            return value
    return "Request failed."


def envelope_exception_handler(exc, context):
    resp = drf_exception_handler(exc, context)
    if resp is None:
        return None  # unhandled -> let Django raise a real 500
    detail = resp.data
    if isinstance(detail, dict):
        # DRF wraps a single message under "detail"; field errors are a dict.
        if set(detail) == {"detail"}:
            message, errors = str(detail["detail"]), None
        else:
            message, errors = _first_error(detail), detail
    elif isinstance(detail, list) and detail:
        message, errors = str(detail[0]), {"detail": detail}
    else:
        message, errors = "Request failed.", detail
    resp.data = {"success": False, "message": message, "errors": errors}
    return resp
