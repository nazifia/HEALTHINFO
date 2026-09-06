"""Outbreak surveillance: spot disease clusters from case-report volume.

Compares the most recent day's case count per disease against a trailing
baseline. A spike = current day well above the historical mean. This is the
one genuinely novel health feature — the data model already carries
disease + time + region, so detection is a query plus a threshold.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import mean, pstdev

from django.db.models import Count
from django.db.models.functions import TruncDay
from django.utils import timezone

from .models import CaseReport

# A day must clear BOTH guards to alarm: enough absolute cases to matter, and
# enough above baseline to be a real signal not noise.
# ponytail: 3/day is the daily equivalent of the old 5/week floor; tune if a
# facility's normal daily volume makes it noisy.
MIN_CASES = 3
Z_THRESHOLD = 2.0  # current day > mean + 2*stdev of prior days


def _daily_counts(reports, days):
    """{disease_id: {"name", "code", "days": [oldest..newest counts]}}.

    Every day in the window gets a bucket, quiet ones included. A day with no
    cases is a zero in the baseline, not a missing entry: drop it and the mean
    is taken over busy days only, which lifts the baseline and hides the very
    spikes this looks for. Daily buckets are sparse where weekly ones were not,
    so the gaps have to be filled.
    """
    since = timezone.now() - timedelta(days=days)
    rows = (
        reports.filter(created_at__gte=since)
        .exclude(disease=None)
        .annotate(period=TruncDay("created_at"))
        .values("disease_id", "disease__name", "disease__icd10_code", "period")
        .annotate(count=Count("id"))
    )
    today = timezone.localdate()
    idx = {today - timedelta(days=i): days - 1 - i for i in range(days)}
    out = {}
    for r in rows:
        i = idx.get(timezone.localtime(r["period"]).date())
        if i is None:
            continue  # the partial extra day the window edge picks up
        d = out.setdefault(
            r["disease_id"],
            {
                "disease_id": r["disease_id"],
                "name": r["disease__name"],
                "icd10_code": r["disease__icd10_code"],
                "days": [0] * days,
            },
        )
        d["days"][i] = r["count"]
    return out


def detect_spikes(reports, days=30):
    """Return diseases whose latest day spikes vs their trailing baseline.

    `reports` is any CaseReport queryset (tenant-scoped or all_objects), so the
    same logic powers a per-tenant alert and the platform-wide one.

    The last bucket is today, so a caller running early in the morning judges a
    few hours of reports against full days.
    ponytail: the 04:00 beat task lives with that; compare the last *complete*
    day if the daily email starts missing outbreaks.
    """
    alerts = []
    for d in _daily_counts(reports, days).values():
        series = d["days"]
        # ponytail: this is window length, not data length — a tenant in its
        # first week baselines against zeros. Track first case date if it bites.
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
                    "current_day": current,
                    "baseline_mean": round(mu, 2),
                    "daily_counts": series,
                }
            )
    alerts.sort(key=lambda a: a["current_day"] - a["baseline_mean"], reverse=True)
    return alerts


def tenant_spikes(days=30):
    return detect_spikes(CaseReport.objects.all(), days)


def platform_spikes(days=30):
    return detect_spikes(CaseReport.all_objects.all(), days)
