"""IDSR weekly epidemiological summary — the canonical collated report.

Nigeria's Integrated Disease Surveillance and Response (IDSR) reports flow up a
tiered hierarchy (health facility → LGA → state → national/NCDC) as weekly
epi-week summaries. Here a *tenant* is the reporting facility and its
``Jurisdiction`` chain is the LGA→state→national tree, so the same data already
collated for dashboards is re-shaped into the standard IDSR line: per epi-week
× disease, cases + deaths + case-fatality rate, with notifiable diseases
flagged for mandatory onward reporting.

IDSR splits that mandatory reporting in two. Most notifiable diseases ride the
weekly summary; the epidemic-prone ones must be notified case by case within 24
hours of suspicion. ``immediate_alerts`` is that second channel — the worklist
of single cases whose 24-hour clock is running.

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
    "epi_week", "disease", "icd10_code", "notifiable", "notify_immediately",
    "cases", "deaths", "case_fatality_rate",
)

# Hours IDSR allows between suspecting an immediately-notifiable case and
# notifying the next tier up.
IMMEDIATE_DEADLINE_HOURS = 24


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
        .values(
            "week", "disease__name", "disease__icd10_code",
            "disease__notifiable", "disease__notify_immediately",
        )
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
                "notify_immediately": r["disease__notify_immediately"],
                "cases": cases,
                "deaths": deaths,
                # CFR: share of cases that died. Core IDSR severity signal.
                "case_fatality_rate": round(deaths / cases, 4) if cases else None,
            }
        )
    return out


ALERT_COLUMNS = (
    "id", "reported_at", "disease", "icd10_code", "facility", "jurisdiction",
    "region", "severity", "outcome", "patient_age_group", "patient_sex",
    "hours_elapsed", "overdue",
)


def immediate_alerts(reports, hours=IMMEDIATE_DEADLINE_HOURS):
    """Single cases of immediately-notifiable disease whose 24-hour clock runs.

    One row per case, not per week: the epidemic-prone diseases are notified up
    the tier the day they are suspected, so a weekly bucket would report them
    too late to matter. Oldest first — the case nearest its deadline is the one
    to send next — and `overdue` marks the ones already past it.

    `hours` widens the window rather than the deadline: the deadline stays 24
    hours, so asking for 72 shows yesterday's misses next to today's work.

    ponytail: elapsed time is measured from when the case was filed, and nothing
    records that a notification went out — every listed case reads as unsent.
    Add a `notified_at` on CaseReport when a facility needs the sent ones to
    drop off this list.
    """
    since = timezone.now() - timedelta(hours=hours)
    rows = (
        reports.filter(disease__notify_immediately=True, created_at__gte=since)
        .select_related("disease", "tenant", "tenant__jurisdiction")
        .order_by("created_at", "id")
    )
    now = timezone.now()
    out = []
    for c in rows:
        elapsed = (now - c.created_at).total_seconds() / 3600
        out.append(
            {
                "id": c.id,
                "reported_at": c.created_at,
                "disease": c.disease.name,
                "icd10_code": c.disease.icd10_code,
                "facility": c.tenant.name if c.tenant_id else "",
                # The LGA that owes the state this notification.
                "jurisdiction": (
                    c.tenant.jurisdiction.name
                    if c.tenant_id and c.tenant.jurisdiction_id else ""
                ),
                "region": c.region,
                "severity": c.severity,
                "outcome": c.outcome,
                "patient_age_group": c.patient_age_group,
                "patient_sex": c.patient_sex,
                "hours_elapsed": round(elapsed, 1),
                "overdue": elapsed > IMMEDIATE_DEADLINE_HOURS,
            }
        )
    return out


def tenant_idsr_report(weeks=8):
    """One facility's (tenant's) IDSR weekly return, plus its 24-hour worklist."""
    reports = CaseReport.objects.all()
    return {
        "weeks": weeks,
        "summary": weekly_summary(reports, weeks),
        "immediate": immediate_alerts(reports),
    }


def platform_idsr_report(weeks=8):
    """Central (NCDC) collation: pool every tenant, then roll case totals all the
    way up the gov hierarchy — LGA → state → national."""
    reports = CaseReport.all_objects.all()
    return {
        "weeks": weeks,
        "summary": weekly_summary(reports, weeks),
        # Centrally the window is a week, not a day: what the tiers below missed
        # is exactly what the centre is watching for.
        "immediate": immediate_alerts(reports, hours=7 * 24),
        "by_local": _rollup_by_tier(reports, Jurisdiction.Level.LOCAL),
        "by_state": _rollup_by_tier(reports, Jurisdiction.Level.STATE),
        "by_national": _rollup_by_tier(reports, Jurisdiction.Level.NATIONAL),
    }
