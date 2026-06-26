"""IDSR weekly epidemiological summary — the canonical collated report.

Nigeria's Integrated Disease Surveillance and Response (IDSR) reports flow up a
tiered hierarchy (health facility → LGA → state → national/NCDC) as weekly
epi-week summaries. Here a *tenant* is the reporting facility and its
``Jurisdiction`` chain is the LGA→state→national tree, so the same data already
collated for dashboards is re-shaped into the standard IDSR line: per epi-week
× disease, cases + deaths + case-fatality rate, with notifiable diseases
flagged for mandatory onward reporting.

Collation, analysis and reporting in one pass:
  * collation — group cases by epi-week and disease (platform view pools every
    tenant via the unscoped manager and rolls totals up the gov hierarchy);
  * analysis  — derive deaths and the case-fatality rate (CFR) per row;
  * reporting — emit the rows in IDSR weekly form, CSV-exportable.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.tenants.models import Jurisdiction

from .models import CaseReport
from .stats import _rollup_by_tier

# Columns of one IDSR weekly summary row, in report order. Reused by the CSV export.
SUMMARY_COLUMNS = (
    "epi_week", "disease", "icd10_code", "notifiable",
    "cases", "deaths", "case_fatality_rate",
)


def _epi_week(dt):
    """ISO epi-week label, e.g. "2026-W26". TruncWeek and ISO weeks both start
    Monday, so the bucket and the label agree."""
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def weekly_summary(reports, weeks=8):
    """IDSR weekly epidemiological summary rows over the trailing `weeks`.

    `reports` is any CaseReport queryset (tenant-scoped or ``all_objects``), so
    the same logic serves a facility's own return and the central NCDC pool.
    Ordered newest week first, then highest case load — the order an epidemiologist
    scans.
    """
    since = timezone.now() - timedelta(weeks=weeks)
    rows = (
        reports.filter(created_at__gte=since)
        .exclude(disease=None)
        .annotate(week=TruncWeek("created_at"))
        .values("week", "disease__name", "disease__icd10_code", "disease__notifiable")
        .annotate(
            cases=Count("id"),
            deaths=Count("id", filter=Q(outcome=CaseReport.Outcome.DECEASED)),
        )
        .order_by("-week", "-cases")
    )
    out = []
    for r in rows:
        cases, deaths = r["cases"], r["deaths"]
        out.append(
            {
                "epi_week": _epi_week(r["week"]),
                "disease": r["disease__name"],
                "icd10_code": r["disease__icd10_code"],
                "notifiable": r["disease__notifiable"],
                "cases": cases,
                "deaths": deaths,
                # CFR: share of cases that died. Core IDSR severity signal.
                "case_fatality_rate": round(deaths / cases, 4) if cases else None,
            }
        )
    return out


def tenant_idsr_report(weeks=8):
    """One facility's (tenant's) IDSR weekly return."""
    return {"weeks": weeks, "summary": weekly_summary(CaseReport.objects.all(), weeks)}


def platform_idsr_report(weeks=8):
    """Central (NCDC) collation: pool every tenant, then roll case totals all the
    way up the gov hierarchy — LGA → state → national."""
    reports = CaseReport.all_objects.all()
    return {
        "weeks": weeks,
        "summary": weekly_summary(reports, weeks),
        "by_local": _rollup_by_tier(reports, Jurisdiction.Level.LOCAL),
        "by_state": _rollup_by_tier(reports, Jurisdiction.Level.STATE),
        "by_national": _rollup_by_tier(reports, Jurisdiction.Level.NATIONAL),
    }
