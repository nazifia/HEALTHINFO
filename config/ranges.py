"""The ?from=&to= date window every dashboard and report endpoint accepts."""
import calendar
from datetime import date

from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError


def date_range(request):
    """Parse ?from=&to= (YYYY-MM-DD) into date objects (None if absent).

    ?year=[&month=] stands in for from/to when neither is sent: one month, or
    the whole year when month is omitted. Bad numbers are a 400, not a 500.
    """
    q = request.query_params
    try:
        start, end = parse_date(q.get("from", "") or ""), parse_date(q.get("to", "") or "")
    except ValueError:  # well-formed but impossible, e.g. 2026-02-30
        raise ValidationError({"from": "From and to must be real dates (YYYY-MM-DD)."})
    if start or end or not (q.get("year") or q.get("month")):
        return start, end
    try:
        year = int(q.get("year") or date.today().year)
        month = int(q["month"]) if q.get("month") else None
        if month is None:
            return date(year, 1, 1), date(year, 12, 31)
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    except ValueError:
        raise ValidationError({"month": "Year and month must be valid numbers."})


def apply_range(qs, start=None, end=None):
    """Filter a queryset to a [start, end] created_at window (date objects)."""
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs
