"""IDSR daily epidemiological summary — the canonical collated report.

Nigeria's Integrated Disease Surveillance and Response (IDSR) reports flow up a
tiered hierarchy (health facility → LGA → state → national/NCDC). Here a
*tenant* is the reporting facility and its ``Jurisdiction`` chain is the
LGA→state→national tree, so the same data already collated for dashboards is
re-shaped into the standard IDSR line: per day × disease, cases + deaths +
case-fatality rate, with notifiable diseases flagged for mandatory onward
reporting.

IDSR splits that mandatory reporting in two. Most notifiable diseases ride the
routine summary; the epidemic-prone ones must be notified case by case within 24
hours of suspicion. ``immediate_alerts`` is that second channel — the worklist
of single cases whose 24-hour clock is running.

Collation, analysis and reporting in one pass:
  * collation — group cases by day and disease (platform view pools every
    tenant via the unscoped manager and rolls totals up the gov hierarchy);
  * analysis  — derive deaths and the case-fatality rate (CFR) per row;
  * reporting — emit the rows in IDSR daily form, CSV-exportable.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDay
from django.utils import timezone

from apps.tenants.models import Jurisdiction

from .models import CaseReport
from .stats import _rollup_by_tier

# Columns of one IDSR daily summary row, in report order. Reused by the CSV export.
SUMMARY_COLUMNS = (
    "date", "disease", "icd10_code", "notifiable", "notify_immediately",
    "cases", "deaths", "case_fatality_rate",
)

# Hours IDSR allows between suspecting an immediately-notifiable case and
# notifying the next tier up.
IMMEDIATE_DEADLINE_HOURS = 24


def daily_summary(reports, days=30):
    """IDSR daily epidemiological summary rows over the trailing `days`.

    `reports` is any CaseReport queryset (tenant-scoped or ``all_objects``), so
    the same logic serves a facility's own return and the central NCDC pool.
    Ordered newest day first, then highest case load — the order an epidemiologist
    scans.
    """
    since = timezone.now() - timedelta(days=days)
    rows = (
        reports.filter(created_at__gte=since)
        .exclude(disease=None)
        .annotate(day=TruncDay("created_at"))
        .values(
            "day", "disease__name", "disease__icd10_code",
            "disease__notifiable", "disease__notify_immediately",
        )
        .annotate(
            cases=Count("id"),
            deaths=Count("id", filter=Q(outcome=CaseReport.Outcome.DECEASED)),
        )
        .order_by("-day", "-cases")
    )
    out = []
    for r in rows:
        cases, deaths = r["cases"], r["deaths"]
        out.append(
            {
                "date": r["day"].date().isoformat(),
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
    "notified_at", "notified_by", "hours_elapsed", "overdue",
)


def immediate_alerts(reports, hours=IMMEDIATE_DEADLINE_HOURS, notified=False):
    """Single cases of immediately-notifiable disease whose 24-hour clock runs.

    One row per case, not per day: the epidemic-prone diseases are notified up
    the tier the hour they are suspected, so even a daily bucket would report
    them too late to matter. Oldest first — the case nearest its deadline is the one
    to send next — and `overdue` marks the ones already past it.

    `hours` widens the window rather than the deadline: the deadline stays 24
    hours, so asking for 72 shows yesterday's misses next to today's work.

    By default this is the worklist: only cases still owed a notification. Pass
    ``notified=True`` for the audit view, which keeps the sent ones in and stops
    their clock at ``notified_at`` — that is what says whether the facility made
    the 24 hours, and it must not keep counting up afterwards.
    """
    since = timezone.now() - timedelta(hours=hours)
    rows = reports.filter(
        disease__notify_immediately=True, created_at__gte=since
    ).select_related(
        "disease", "tenant", "tenant__jurisdiction", "notified_by"
    ).order_by("created_at", "id")
    if not notified:
        rows = rows.filter(notified_at=None)
    now = timezone.now()
    out = []
    for c in rows:
        # A sent case is judged on how long it took, not on how long ago it was.
        elapsed = ((c.notified_at or now) - c.created_at).total_seconds() / 3600
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
                "notified_at": c.notified_at,
                "notified_by": c.notified_by.username if c.notified_by_id else "",
                "hours_elapsed": round(elapsed, 1),
                "overdue": elapsed > IMMEDIATE_DEADLINE_HOURS,
            }
        )
    return out


def timeliness(reports, hours=72):
    """How the immediate notifications in the window went: sent, late, still owed.

    The compliance line an IDSR review asks for, derived from the same rows the
    worklist is built from rather than counted a second way.

    The window has to be wider than the deadline or the line is meaningless: a
    case can only be late once it is past 24 hours, so a 24-hour window would
    report `late` as 0 forever. 72 hours shows the last two days of misses
    beside today's work.
    """
    rows = immediate_alerts(reports, hours=hours, notified=True)
    sent = [r for r in rows if r["notified_at"] is not None]
    return {
        "window_hours": hours,
        "cases": len(rows),
        "notified": len(sent),
        "on_time": len([r for r in sent if not r["overdue"]]),
        "late": len([r for r in sent if r["overdue"]]),
        "pending": len(rows) - len(sent),
    }


def tenant_idsr_report(days=30):
    """One facility's (tenant's) IDSR daily return, plus its 24-hour worklist."""
    reports = CaseReport.objects.all()
    return {
        "days": days,
        "summary": daily_summary(reports, days),
        "immediate": immediate_alerts(reports),
        "timeliness": timeliness(reports),
    }


def platform_idsr_report(days=30):
    """Central (NCDC) collation: pool every tenant, then roll case totals all the
    way up the gov hierarchy — LGA → state → national."""
    reports = CaseReport.all_objects.all()
    return {
        "days": days,
        "summary": daily_summary(reports, days),
        # Centrally the window is 48 hours, not 24: what the tiers below missed
        # yesterday is exactly what the centre is watching for.
        "immediate": immediate_alerts(reports, hours=48),
        "timeliness": timeliness(reports),
        "by_local": _rollup_by_tier(reports, Jurisdiction.Level.LOCAL),
        "by_state": _rollup_by_tier(reports, Jurisdiction.Level.STATE),
        "by_national": _rollup_by_tier(reports, Jurisdiction.Level.NATIONAL),
    }
