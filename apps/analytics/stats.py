"""Dashboard aggregations. Kept out of views so they're unit-testable.

Every public function takes an optional (start, end) date window so the same
rollup serves "last 30 days", "this quarter", or all-time without new code.
"""
from datetime import timedelta
from statistics import median

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDay, TruncWeek
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Disease, Medication
from apps.tenants.current import get_current_tenant
from apps.tenants.models import Jurisdiction, Tenant
from .nigeria import region_state

from .models import (
    AdverseDrugReaction,
    AiInteraction,
    AnalyticsEvent,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    StockReport,
    VitalEvent,
)

_OBJECT_MODELS = {"disease": Disease, "medication": Medication}


def apply_range(qs, start=None, end=None):
    """Filter a queryset to a [start, end] created_at window (date objects)."""
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs


def _series(qs, days=30, bucket="day"):
    """Time-series counts per day/week over the trailing window.

    Returns [{"period": iso-date, "count": n}] ordered oldest→newest. Empty
    buckets are omitted (caller can densify if it needs a continuous axis).
    ponytail: DB-side TruncDay/Week; gap-filling is a frontend concern.
    """
    since = timezone.now() - timedelta(days=days)
    trunc = TruncWeek if bucket == "week" else TruncDay
    rows = (
        qs.filter(created_at__gte=since)
        .annotate(period=trunc("created_at"))
        .values("period")
        .annotate(count=Count("id"))
        .order_by("period")
    )
    return [
        {"period": r["period"].date().isoformat(), "count": r["count"]} for r in rows
    ]


def _popular(events, object_type, limit=10):
    rows = list(
        events.filter(event_type="view", object_type=object_type)
        .values("object_id")
        .annotate(count=Count("id"))
        .order_by("-count")[:limit]
    )
    model = _OBJECT_MODELS[object_type]
    name_field = "name" if object_type == "disease" else "generic_name"
    ids = [r["object_id"] for r in rows]  # only resolve names we actually show
    names = dict(model.objects.filter(id__in=ids).values_list("id", name_field))
    return [
        {"id": r["object_id"], "name": names.get(r["object_id"], "?"), "views": r["count"]}
        for r in rows
    ]


def _content_gaps(events, limit=10):
    """Most-repeated searches that returned nothing — what to write next."""
    return list(
        events.filter(event_type="search", result_count=0)
        .exclude(query="")
        .values("query")
        .annotate(count=Count("id"))
        .order_by("-count")[:limit]
    )


def _ai_feedback(interactions):
    """Thumbs tally on RAG answers — answer-quality signal."""
    return {
        "up": interactions.filter(feedback=AiInteraction.UP).count(),
        "down": interactions.filter(feedback=AiInteraction.DOWN).count(),
    }


def tenant_stats(start=None, end=None):
    """Current-tenant dashboard. Relies on the tenant-scoped manager."""
    events = apply_range(AnalyticsEvent.objects.all(), start, end)
    ai = apply_range(AiInteraction.objects.all(), start, end)
    since = timezone.now() - timedelta(days=30)
    return {
        "total_searches": events.filter(event_type="search").count(),
        "content_gaps": _content_gaps(events),
        "active_users": events.filter(created_at__gte=since)
        .exclude(user=None)
        .values("user")
        .distinct()
        .count(),
        "top_searches": list(
            events.filter(event_type="search")
            .exclude(query="")
            .values("query")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "popular_diseases": _popular(events, "disease"),
        "popular_medications": _popular(events, "medication"),
        "ai_feedback": _ai_feedback(ai),
        "search_trend": _series(events.filter(event_type="search"), days=30),
    }


def funnel_stats(start=None, end=None):
    """search → view → case-report counts + conversion ratios for the window."""
    events = apply_range(AnalyticsEvent.objects.all(), start, end)
    cases = apply_range(CaseReport.objects.all(), start, end).count()
    searches = events.filter(event_type="search").count()
    views = events.filter(event_type="view").count()

    def ratio(a, b):
        return round(a / b, 3) if b else None

    return {
        "searches": searches,
        "views": views,
        "case_reports": cases,
        "view_per_search": ratio(views, searches),
        "case_per_view": ratio(cases, views),
    }


def ai_quality_stats(start=None, end=None):
    """RAG answer-quality dashboard from stored AiInteractions."""
    qs = apply_range(AiInteraction.objects.all(), start, end)
    total = qs.count()
    answered = qs.exclude(answer__isnull=True).exclude(answer="").count()
    down = qs.filter(feedback=AiInteraction.DOWN).count()
    rated = qs.exclude(feedback="").count()
    return {
        "total": total,
        "answered": answered,
        "retrieval_only": total - answered,  # no API key / no synthesis
        "feedback": _ai_feedback(qs),
        "unrated": total - rated,
        "downvote_rate": round(down / rated, 3) if rated else None,
        "top_downvoted": list(
            qs.filter(feedback=AiInteraction.DOWN)
            .values("question")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
    }


def retention_stats(weeks=8):
    """Active distinct users per week — engagement curve (tenant-scoped)."""
    events = AnalyticsEvent.objects.exclude(user=None)
    since = timezone.now() - timedelta(weeks=weeks)
    rows = (
        events.filter(created_at__gte=since)
        .annotate(period=TruncWeek("created_at"))
        .values("period")
        .annotate(users=Count("user", distinct=True))
        .order_by("period")
    )
    return [
        {"period": r["period"].date().isoformat(), "active_users": r["users"]}
        for r in rows
    ]


def _fold_region_to_state(region_rows):
    """Roll a by_region list ([{region, count}]) up to state. Region is stored
    "LGA, State"; sum every LGA into its state. Blank/unparseable → "—"."""
    totals = {}
    for r in region_rows:
        st = region_state(r["region"] or "") or "—"
        totals[st] = totals.get(st, 0) + r["count"]
    return [
        {"state": name, "count": c}
        for name, c in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def _case_breakdown(reports):
    """Counts grouped by the dimensions an analyst slices on."""
    def by(field):
        return list(
            reports.values(field).annotate(count=Count("id")).order_by("-count")
        )
    total = reports.count()
    deaths = reports.filter(outcome=CaseReport.Outcome.DECEASED).count()
    return {
        "total": total,
        # IDSR analysis metrics: deaths and case-fatality rate (deaths / cases).
        "deaths": deaths,
        "case_fatality_rate": round(deaths / total, 4) if total else None,
        "by_severity": by("severity"),
        "by_outcome": by("outcome"),
        "by_age_group": by("patient_age_group"),
        "by_region": by("region"),
        "by_region_state": _fold_region_to_state(by("region")),
        "top_diseases": list(
            reports.exclude(disease=None)
            .values("disease__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "case_trend": _series(reports, days=90, bucket="week"),
    }


def case_report_stats(start=None, end=None):
    """Current-tenant case-report rollup (tenant-scoped manager)."""
    return _case_breakdown(apply_range(CaseReport.objects.all(), start, end))


def _normalized_diseases(reports, limit=20):
    """Collate cases across tenants by ICD-10 code, not free-text name.

    Same disease is spelled differently per tenant ("Type 2 diabetes" vs
    "T2DM"); the shared ICD-10 code is the join key that makes cross-tenant
    totals correct. Rows with no code fall back to their name.
    """
    coded = (
        reports.exclude(disease=None)
        .exclude(disease__icd10_code="")
        .values("disease__icd10_code")
        .annotate(count=Count("id"))
        .order_by("-count")[:limit]
    )
    return [
        {"icd10_code": r["disease__icd10_code"], "count": r["count"]} for r in coded
    ]


def _rollup_by_tier(reports, level):
    """Fold per-tenant counts up the jurisdiction tree to `level`.

    Group once in SQL by the tenant's own jurisdiction, then walk each up to its
    state/national ancestor in Python and sum. Tree is tiny (one row per gov
    unit), so the walk is cheap — no recursive CTE needed.
    """
    rows = (
        reports.exclude(tenant__jurisdiction=None)
        .values("tenant__jurisdiction")
        .annotate(count=Count("id"))
    )
    juris = {j.id: j for j in Jurisdiction.objects.all()}
    totals = {}
    for r in rows:
        node = juris.get(r["tenant__jurisdiction"])
        anc = node.ancestor(level) if node else None
        if anc is not None:
            totals[anc.name] = totals.get(anc.name, 0) + r["count"]
    return [
        {level: name, "count": c}
        for name, c in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def platform_case_report_stats(start=None, end=None):
    """Super-admin case-report rollup across all tenants — the central collation."""
    reports = apply_range(CaseReport.all_objects.all(), start, end)
    stats = _case_breakdown(reports)
    stats["by_tenant"] = list(
        reports.values("tenant__name").annotate(count=Count("id")).order_by("-count")[:20]
    )
    # Cross-tenant collation keyed on ICD-10 (fixes name-collision double counting).
    stats["by_icd10"] = _normalized_diseases(reports)
    # Geographic rollup up the full gov hierarchy: tenant → local → state → national.
    stats["by_local"] = _rollup_by_tier(reports, Jurisdiction.Level.LOCAL)
    stats["by_state"] = _rollup_by_tier(reports, Jurisdiction.Level.STATE)
    stats["by_national"] = _rollup_by_tier(reports, Jurisdiction.Level.NATIONAL)
    return stats


def _merge_tier(qs_a, qs_b, level):
    """Roll both report streams up the jurisdiction tree to `level` and sum.

    Same fold as _rollup_by_tier, applied per-stream then merged so case reports
    and ADRs land in one tenant→local→state total.
    """
    out = {}
    for row in _rollup_by_tier(qs_a, level) + _rollup_by_tier(qs_b, level):
        out[row[level]] = out.get(row[level], 0) + row["count"]
    return [
        {level: name, "count": c}
        for name, c in sorted(out.items(), key=lambda kv: -kv[1])
    ]


def _merge_counts(rows_a, rows_b, key):
    """Sum two grouped-count streams (case reports + ADRs) on the same key.

    Each stream is a `.values(key).annotate(count=...)` queryset; null/blank
    labels collapse to "—" so an unknown reporter/region still shows up.
    """
    out = {}
    for r in list(rows_a) + list(rows_b):
        label = r[key] or "—"
        out[label] = out.get(label, 0) + r["count"]
    return [
        {key: name, "count": c}
        for name, c in sorted(out.items(), key=lambda kv: -kv[1])
    ]


def report_sources(start=None, end=None, platform=False):
    """Where reports originate — the source behind every collated number.

    Pools both report streams (case reports + adverse-drug reactions) and groups
    by who filed them and from where: reporter, region, and (platform) tenant.
    platform=True collates across all tenants via the unscoped manager.
    """
    cases = CaseReport.all_objects if platform else CaseReport.objects
    adrs = AdverseDrugReaction.all_objects if platform else AdverseDrugReaction.objects
    cases = apply_range(cases.all(), start, end)
    adrs = apply_range(adrs.all(), start, end)

    def grouped(qs, field):
        return qs.values(field).annotate(count=Count("id"))

    out = {
        "total_cases": cases.count(),
        "total_adrs": adrs.count(),
        "by_region": _merge_counts(
            grouped(cases, "region"), grouped(adrs, "region"), "region"
        ),
        "by_region_state": _fold_region_to_state(
            _merge_counts(grouped(cases, "region"), grouped(adrs, "region"), "region")
        ),
        "by_reporter": _merge_counts(
            grouped(cases, "reporter__username"),
            grouped(adrs, "reporter__username"),
            "reporter__username",
        ),
    }
    if platform:
        out["by_tenant"] = _merge_counts(
            grouped(cases, "tenant__name"),
            grouped(adrs, "tenant__name"),
            "tenant__name",
        )
        # Roll the pooled stream up the gov hierarchy: tenant → local → state → national.
        out["by_local"] = _merge_tier(cases, adrs, Jurisdiction.Level.LOCAL)
        out["by_state"] = _merge_tier(cases, adrs, Jurisdiction.Level.STATE)
        out["by_national"] = _merge_tier(cases, adrs, Jurisdiction.Level.NATIONAL)
    return out


def benchmark_stats():
    """Current tenant's case load vs the anonymized platform median.

    Lets a tenant see "are we high or low vs the network" without exposing any
    other tenant's identity or raw numbers.
    """
    tenant = get_current_tenant()
    per_tenant = dict(
        CaseReport.all_objects.exclude(tenant=None)  # skip global rows, not a real tenant
        .values_list("tenant")
        .annotate(count=Count("id"))
        .values_list("tenant", "count")
    )
    counts = list(per_tenant.values())
    mine = per_tenant.get(tenant.id, 0) if tenant else 0
    return {
        "your_case_reports": mine,
        "platform_median": median(counts) if counts else 0,
        "platform_max": max(counts) if counts else 0,
        "tenants_compared": len(counts),
    }


def platform_stats(start=None, end=None):
    """Super-admin dashboard across all tenants (bypasses scoping)."""
    events = apply_range(AnalyticsEvent.all_objects.all(), start, end)
    return {
        "total_tenants": Tenant.objects.count(),
        "total_users": User.objects.count(),
        "total_searches": events.filter(event_type="search").count(),
        "content_gaps": _content_gaps(events),
        "searches_by_tenant": list(
            events.filter(event_type="search")
            .values("tenant__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        ),
        "ai_feedback": _ai_feedback(apply_range(AiInteraction.all_objects.all(), start, end)),
        "search_trend": _series(events.filter(event_type="search"), days=90, bucket="week"),
        "adverse_reactions": adr_stats(platform=True),
    }


def adr_stats(start=None, end=None, platform=False):
    """Adverse-drug-reaction rollup. platform=True collates across tenants."""
    manager = AdverseDrugReaction.all_objects if platform else AdverseDrugReaction.objects
    reports = apply_range(manager.all(), start, end)

    def by(field):
        return list(reports.values(field).annotate(count=Count("id")).order_by("-count"))

    out = {
        "total": reports.count(),
        "by_severity": by("severity"),
        "by_outcome": by("outcome"),
        "top_medications": list(
            reports.values("medication__generic_name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "top_reactions": list(
            reports.values("reaction").annotate(count=Count("id")).order_by("-count")[:10]
        ),
        "trend": _series(reports, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = by("tenant__name")
        out["by_local"] = _rollup_by_tier(reports, Jurisdiction.Level.LOCAL)
        out["by_state"] = _rollup_by_tier(reports, Jurisdiction.Level.STATE)
        out["by_national"] = _rollup_by_tier(reports, Jurisdiction.Level.NATIONAL)
    return out


def _manager(model, platform):
    """Tenant-scoped vs cross-tenant manager — the one knob every platform rollup
    toggles. all_objects bypasses scoping (super-admin collation)."""
    return model.all_objects if platform else model.objects


def _grouped(qs, field, limit=None):
    rows = qs.values(field).annotate(count=Count("id")).order_by("-count")
    return list(rows[:limit] if limit else rows)


def lab_stats(start=None, end=None, platform=False):
    """Lab-result rollup incl. the antimicrobial-resistance (AMR) signal.

    AMR rate = resistant isolates / all isolates with a susceptibility result,
    sliced by organism and by antibiotic. platform=True collates across tenants.
    """
    reports = apply_range(_manager(LabResult, platform).all(), start, end)
    tested = reports.exclude(susceptibility="")  # rows that ran an AST
    resistant = tested.filter(susceptibility=LabResult.Susceptibility.RESISTANT)

    def amr_by(field):
        """Resistance rate per `field`: resistant count / tested count."""
        totals = dict(tested.values_list(field).annotate(n=Count("id")))
        res = dict(resistant.values_list(field).annotate(n=Count("id")))
        out = [
            {
                field: key or "—",
                "tested": n,
                "resistant": res.get(key, 0),
                "resistance_rate": round(res.get(key, 0) / n, 4) if n else None,
            }
            for key, n in totals.items()
        ]
        out.sort(key=lambda r: r["resistance_rate"] or 0, reverse=True)
        return out

    tested_n = tested.count()
    out = {
        "total": reports.count(),
        "by_flag": _grouped(reports, "flag"),
        "isolates_tested": tested_n,
        "resistant": resistant.count(),
        "amr_rate": round(resistant.count() / tested_n, 4) if tested_n else None,
        "amr_by_organism": amr_by("organism"),
        "amr_by_antibiotic": amr_by("antibiotic"),
        "top_organisms": _grouped(reports.exclude(organism=""), "organism", 10),
        "by_region": _grouped(reports, "region"),
        "trend": _series(reports, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
    return out


def chw_stats(start=None, end=None, platform=False):
    """Community-health-worker field reports: out-of-facility care volume,
    danger signs and referral rate."""
    reports = apply_range(_manager(CommunityHealthReport, platform).all(), start, end)
    total = reports.count()
    referred = reports.filter(referred=True).count()
    out = {
        "total": total,
        "danger_signs": reports.filter(danger_signs=True).count(),
        "referred": referred,
        "referral_rate": round(referred / total, 4) if total else None,
        "by_type": _grouped(reports, "report_type"),
        "by_region_state": _fold_region_to_state(_grouped(reports, "region")),
        "trend": _series(reports, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
    return out


def facility_stats(start=None, end=None, platform=False):
    """Health-service KPIs averaged across facility snapshots: bed occupancy,
    waiting time, staffing and total throughput."""
    reports = apply_range(_manager(FacilityMetric, platform).all(), start, end)
    agg = reports.aggregate(
        beds_total=Sum("beds_total"),
        beds_occupied=Sum("beds_occupied"),
        avg_wait=Avg("avg_wait_minutes"),
        avg_staff=Avg("staff_on_duty"),
        patients=Sum("patients_treated"),
    )
    beds_total = agg["beds_total"] or 0
    out = {
        "snapshots": reports.count(),
        "occupancy_rate": round(agg["beds_occupied"] / beds_total, 4) if beds_total else None,
        "avg_wait_minutes": round(agg["avg_wait"], 1) if agg["avg_wait"] is not None else None,
        "avg_staff_on_duty": round(agg["avg_staff"], 1) if agg["avg_staff"] is not None else None,
        "patients_treated": agg["patients"] or 0,
        "trend": _series(reports, days=90, bucket="week"),
    }
    if platform:
        # Throughput per facility — who is busiest.
        out["by_tenant"] = list(
            reports.values("tenant__name")
            .annotate(count=Sum("patients_treated"))
            .order_by("-count")[:20]
        )
    return out


def insurance_stats(start=None, end=None, platform=False):
    """Insurance-claim rollup: volume, cost and approval rate by status &
    diagnosis."""
    claims = apply_range(_manager(InsuranceClaim, platform).all(), start, end)
    total = claims.count()
    decided = claims.filter(
        status__in=[InsuranceClaim.Status.APPROVED, InsuranceClaim.Status.REJECTED,
                    InsuranceClaim.Status.PAID]
    ).count()
    approved = claims.filter(
        status__in=[InsuranceClaim.Status.APPROVED, InsuranceClaim.Status.PAID]
    ).count()
    out = {
        "total": total,
        "total_amount": float(claims.aggregate(s=Sum("amount"))["s"] or 0),
        "approval_rate": round(approved / decided, 4) if decided else None,
        "by_status": _grouped(claims, "status"),
        "top_diagnoses": list(
            claims.exclude(diagnosis=None)
            .values("diagnosis__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "by_region_state": _fold_region_to_state(_grouped(claims, "region")),
        "trend": _series(claims, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(claims, "tenant__name", 20)
    return out


def appointment_stats(start=None, end=None, platform=False):
    """Appointment utilization: in-person vs telemedicine split and no-show rate."""
    appts = apply_range(_manager(Appointment, platform).all(), start, end)
    total = appts.count()
    # No-show rate is over appointments that were due (not still scheduled/cancelled).
    attended = appts.filter(status=Appointment.Status.COMPLETED).count()
    no_show = appts.filter(status=Appointment.Status.NO_SHOW).count()
    due = attended + no_show
    out = {
        "total": total,
        "telemedicine": appts.filter(mode=Appointment.Mode.TELEMEDICINE).count(),
        "no_show_rate": round(no_show / due, 4) if due else None,
        "by_mode": _grouped(appts, "mode"),
        "by_status": _grouped(appts, "status"),
        "trend": _series(appts, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(appts, "tenant__name", 20)
    return out


def immunization_stats(start=None, end=None, platform=False):
    """Vaccination coverage rollup: doses by vaccine, region and age band."""
    reports = apply_range(_manager(Immunization, platform).all(), start, end)
    out = {
        "total_doses": reports.count(),
        "by_vaccine": _grouped(reports, "vaccine", 20),
        "by_age_group": _grouped(reports, "patient_age_group"),
        "by_region": _grouped(reports, "region"),
        "by_region_state": _fold_region_to_state(_grouped(reports, "region")),
        "trend": _series(reports, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
        out["by_state"] = _rollup_by_tier(reports, Jurisdiction.Level.STATE)
        out["by_national"] = _rollup_by_tier(reports, Jurisdiction.Level.NATIONAL)
    return out


def vital_stats(start=None, end=None, platform=False):
    """Vital-registration rollup with maternal & infant mortality.

    Maternal mortality ratio = maternal deaths per 100 000 live births.
    Infant mortality rate     = infant deaths per 1 000 live births.
    Rates are None when there are no recorded births (no denominator).
    """
    events = apply_range(_manager(VitalEvent, platform).all(), start, end)
    births = events.filter(event_type=VitalEvent.Kind.BIRTH).count()
    deaths = events.filter(event_type=VitalEvent.Kind.DEATH)
    deaths_n = deaths.count()
    maternal = deaths.filter(maternal_death=True).count()
    infant = deaths.filter(infant_death=True).count()
    out = {
        "births": births,
        "deaths": deaths_n,
        "maternal_deaths": maternal,
        "infant_deaths": infant,
        # Standard demographic ratios; per-birth so they compare across regions.
        "maternal_mortality_ratio": round(maternal / births * 100000, 1) if births else None,
        "infant_mortality_rate": round(infant / births * 1000, 1) if births else None,
        "deaths_by_cause": _grouped(deaths.exclude(cause=None), "cause__name", 10),
        "by_region": _fold_region_to_state(_grouped(events, "region")),
        "birth_trend": _series(
            events.filter(event_type=VitalEvent.Kind.BIRTH), days=90, bucket="week"
        ),
        "death_trend": _series(deaths, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(events, "tenant__name", 20)
        out["by_state"] = _rollup_by_tier(deaths, Jurisdiction.Level.STATE)
    return out


def stock_stats(start=None, end=None, platform=False):
    """Pharmacy stock & usage rollup: live shortages and consumption trends.

    ``shortages`` is the actionable list — medications flagged stocked-out, most
    recent first — so central can target resupply.
    """
    reports = apply_range(_manager(StockReport, platform).all(), start, end)
    shortages = reports.filter(shortage=True)
    out = {
        "total_reports": reports.count(),
        "shortage_count": shortages.count(),
        "shortages": list(
            shortages.values(
                "medication__generic_name", "region", "on_hand", "created_at"
            ).order_by("-created_at")[:50]
        ),
        "top_consumed": list(
            reports.values("medication__generic_name")
            .annotate(consumed=Sum("consumed"))
            .order_by("-consumed")[:10]
        ),
        "by_region": _grouped(reports, "region"),
        "trend": _series(reports, days=90, bucket="week"),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
    return out
