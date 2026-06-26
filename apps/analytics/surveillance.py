"""Outbreak surveillance: spot disease clusters from case-report volume.

Compares the most recent week's case count per disease against a trailing
baseline. A spike = current week well above the historical mean. This is the
one genuinely novel health feature — the data model already carries
disease + time + region, so detection is a query plus a threshold.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import mean, pstdev

from django.db.models import Count
from django.db.models.functions import TruncWeek
from django.utils import timezone

from .models import CaseReport

# A week must clear BOTH guards to alarm: enough absolute cases to matter, and
# enough above baseline to be a real signal not noise.
MIN_CASES = 5
Z_THRESHOLD = 2.0  # current week > mean + 2*stdev of prior weeks


def _weekly_counts(reports, weeks):
    """{disease_id: {"name", "code", "weeks": [oldest..newest counts]}}."""
    since = timezone.now() - timedelta(weeks=weeks)
    rows = (
        reports.filter(created_at__gte=since)
        .exclude(disease=None)
        .annotate(period=TruncWeek("created_at"))
        .values("disease_id", "disease__name", "disease__icd10_code", "period")
        .annotate(count=Count("id"))
        .order_by("period")
    )
    periods = sorted({r["period"] for r in rows})
    idx = {p: i for i, p in enumerate(periods)}
    out = {}
    for r in rows:
        d = out.setdefault(
            r["disease_id"],
            {
                "disease_id": r["disease_id"],
                "name": r["disease__name"],
                "icd10_code": r["disease__icd10_code"],
                "weeks": [0] * len(periods),
            },
        )
        d["weeks"][idx[r["period"]]] = r["count"]
    return out


def detect_spikes(reports, weeks=8):
    """Return diseases whose latest week spikes vs their trailing baseline.

    `reports` is any CaseReport queryset (tenant-scoped or all_objects), so the
    same logic powers a per-tenant alert and the platform-wide one.
    """
    alerts = []
    for d in _weekly_counts(reports, weeks).values():
        series = d["weeks"]
        if len(series) < 3:
            continue  # not enough history to call a baseline
        current, baseline = series[-1], series[:-1]
        if current < MIN_CASES:
            continue
        mu = mean(baseline)
        sigma = pstdev(baseline)
        # sigma==0 (flat baseline): any jump past MIN_CASES counts as a spike.
        threshold = mu + Z_THRESHOLD * sigma if sigma else mu
        if current > threshold and current > mu:
            alerts.append(
                {
                    "disease_id": d["disease_id"],
                    "name": d["name"],
                    "icd10_code": d["icd10_code"],
                    "current_week": current,
                    "baseline_mean": round(mu, 2),
                    "weekly_counts": series,
                }
            )
    alerts.sort(key=lambda a: a["current_week"] - a["baseline_mean"], reverse=True)
    return alerts


def tenant_spikes(weeks=8):
    return detect_spikes(CaseReport.objects.all(), weeks)


def platform_spikes(weeks=8):
    return detect_spikes(CaseReport.all_objects.all(), weeks)
