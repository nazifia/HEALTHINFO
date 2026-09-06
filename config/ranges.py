"""The ?from=&to= date window every dashboard and report endpoint accepts."""
from django.utils.dateparse import parse_date


def date_range(request):
    """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD into date objects (None if absent)."""
    return (
        parse_date(request.query_params.get("from", "") or ""),
        parse_date(request.query_params.get("to", "") or ""),
    )


def apply_range(qs, start=None, end=None):
    """Filter a queryset to a [start, end] created_at window (date objects)."""
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs
