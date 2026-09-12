"""Dashboard aggregations. Kept out of views so they're unit-testable.

Every public function takes an optional (start, end) date window so the same
rollup serves "last 30 days", "this quarter", or all-time without new code.
"""
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.db.models import (
    Avg,
    Count,
    DateField,
    DurationField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import TruncDate, TruncDay, TruncMonth, TruncYear
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Disease, Medication
from apps.pos.models import ReturnRecord, Sale, SaleItem
from apps.prescriptions.models import PrescriptionItem
from apps.tenants.current import get_current_tenant
from apps.tenants.models import Jurisdiction, Tenant
from config.ranges import apply_range
from .nigeria import region_state

from .models import (
    AdverseDrugReaction,
    AiInteraction,
    AnalyticsEvent,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    Consultation,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    Prescription,
    StockReport,
    VitalEvent,
)

_OBJECT_MODELS = {"disease": Disease, "medication": Medication}

ZERO = Decimal("0.00")

# An order that reached the patient. A partial fill counts: some of the drug
# was handed over, so the prescription is not an unfilled one.
_RX_FILLED = (Prescription.Status.DISPENSED, Prescription.Status.PARTIAL)


def _series(qs, days=30):
    """Time-series counts per day over the trailing window.

    Returns [{"period": iso-date, "count": n}] ordered oldest→newest. Empty
    buckets are omitted (caller can densify if it needs a continuous axis).
    ponytail: DB-side TruncDay; gap-filling is a frontend concern.
    """
    since = timezone.now() - timedelta(days=days)
    rows = (
        qs.filter(created_at__gte=since)
        .annotate(period=TruncDay("created_at"))
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


def tenant_stats(start=None, end=None):
    """Current-tenant dashboard. Relies on the tenant-scoped manager."""
    events = apply_range(AnalyticsEvent.objects.all(), start, end)
    since = timezone.now() - timedelta(days=30)
    return {
        "content_gaps": _content_gaps(events),
        "active_users": events.filter(created_at__gte=since)
        .exclude(user=None)
        .values("user")
        .distinct()
        .count(),
        "popular_diseases": _popular(events, "disease"),
        "popular_medications": _popular(events, "medication"),
        "search_trend": _series(events.filter(event_type="search"), days=30),
        **_prescribing_rollup(start, end),
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


def retention_stats(days=30):
    """Active distinct users per day — engagement curve (tenant-scoped)."""
    events = AnalyticsEvent.objects.exclude(user=None)
    since = timezone.now() - timedelta(days=days)
    rows = (
        events.filter(created_at__gte=since)
        .annotate(period=TruncDay("created_at"))
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


def _prescriptions_for(reports):
    """Orders written for a set of case reports.

    ``reports`` is already scoped — tenant-scoped for a tenant rollup, unscoped
    for the platform one — so joining through it carries that scope over and
    the unscoped manager is safe here.
    """
    return Prescription.all_objects.filter(case_report__in=reports)


def _prescribed_for(reports, limit=10):
    """What was actually prescribed against these diagnoses.

    Reads the orders, not ``CaseReport.medications``: the M2M records only that
    a drug was involved in the case, while a Prescription is the order that was
    written, with a status saying whether it was dispensed.
    """
    rows = (
        _prescriptions_for(reports)
        .values("medication__generic_name")
        .annotate(
            count=Count("id"),
            dispensed=Count("id", filter=Q(status__in=_RX_FILLED)),
        )
        .order_by("-count")[:limit]
    )
    return [
        {"medication": r["medication__generic_name"], "count": r["count"],
         "dispensed": r["dispensed"]}
        for r in rows
    ]


def _diagnosis_pairs(rx, limit=20):
    """Prescribed drugs collated under the diagnosis they were written for.

    Orders with no linked case report are kept under "—" rather than dropped:
    a drug written with no recorded reason is a gap worth seeing, and hiding it
    would make the pair counts add up to less than the total.

    The ICD-10 code rides along because the disease *name* is spelled
    differently per tenant; the code is the join key that keeps a central
    "what is prescribed for this diagnosis" total correct.
    """
    rows = (
        rx.values(
            "case_report__disease__name",
            "case_report__disease__icd10_code",
            "medication__generic_name",
        )
        .annotate(
            count=Count("id"),
            dispensed=Count("id", filter=Q(status__in=_RX_FILLED)),
        )
        .order_by("-count")[:limit]
    )
    return [
        {"diagnosis": r["case_report__disease__name"] or "—",
         "icd10_code": r["case_report__disease__icd10_code"] or "",
         "medication": r["medication__generic_name"],
         "count": r["count"],
         "dispensed": r["dispensed"]}
        for r in rows
    ]


def _prescribing_rollup(start=None, end=None, platform=False, jurisdiction=None):
    """The clinical half of a dashboard: diagnoses, and the drugs written for them.

    The dashboards otherwise report searching and AI answers, which say nothing
    about what was treated. These two rows do, and both carry the dispensed
    count next to the written one, because an order written is not an order
    handed over.
    """
    rx = apply_range(_scoped(Prescription, platform, jurisdiction), start, end)
    rows = (
        rx.values("case_report__disease__name")
        .annotate(
            count=Count("id"),
            dispensed=Count("id", filter=Q(status__in=_RX_FILLED)),
        )
        .order_by("-count")[:10]
    )
    return {
        # Orders with no case linked stay under "—" here for the same reason as
        # in the pairs: a drug with no recorded reason is a gap worth seeing.
        "top_diagnoses": [
            {"diagnosis": r["case_report__disease__name"] or "—",
             "count": r["count"], "dispensed": r["dispensed"]}
            for r in rows
        ],
        # More pairs than a dashboard panel draws: tapping a diagnosis
        # filters this list client-side, and a top-10 cut would leave the
        # quieter diagnoses with nothing behind their bar.
        "by_diagnosis_medication": _diagnosis_pairs(rx, limit=30),
    }


def _case_breakdown(reports):
    """Counts grouped by the dimensions an analyst slices on."""
    total = reports.count()
    deaths = reports.filter(outcome=CaseReport.Outcome.DECEASED).count()
    return {
        "total": total,
        # IDSR analysis metrics: deaths and case-fatality rate (deaths / cases).
        "deaths": deaths,
        "case_fatality_rate": round(deaths / total, 4) if total else None,
        "by_severity": _grouped(reports, "severity"),
        "by_outcome": _grouped(reports, "outcome"),
        "by_age_group": _grouped(reports, "patient_age_group"),
        "by_sex": _by_sex(reports),
        "by_region": _grouped(reports, "region"),
        "by_region_state": _fold_region_to_state(_grouped(reports, "region")),
        "top_diseases": list(
            reports.exclude(disease=None)
            .values("disease__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "case_trend": _series(reports, days=90),
        # The other half of the same picture: what was prescribed against these
        # diagnoses, so a case rollup no longer stops at the diagnosis.
        "top_prescribed": _prescribed_for(reports),
    }


def case_report_stats(start=None, end=None):
    """Current-tenant case-report rollup (tenant-scoped manager)."""
    return _case_breakdown(apply_range(CaseReport.objects.all(), start, end))


def _normalized_diseases(reports, limit=20):
    """Collate cases across tenants by ICD-10 code, and label them by name.

    Same disease is spelled differently per tenant ("Type 2 diabetes" vs
    "T2DM"); the shared ICD-10 code is the join key that makes cross-tenant
    totals correct. Grouping still keys on the code, but a code is not a thing
    anyone reads, so each row also carries a name: whichever spelling the most
    cases were filed under, so the label reads the way most of the country
    writes it. Ties break alphabetically, so the same data names itself the
    same way twice. The code rides along for a reader who wants the
    unambiguous identity behind the name.

    The database groups by (code, name) and the fold to one row per code
    happens here: picking a modal value per group is not something the ORM
    expresses, and the row count is bounded by the distinct diseases, not by
    the cases.
    """
    spellings = (
        reports.exclude(disease=None)
        .exclude(disease__icd10_code="")
        .values("disease__icd10_code", "disease__name")
        .annotate(count=Count("id"))
    )
    totals, names = {}, {}
    for r in spellings:
        code, name, n = r["disease__icd10_code"], r["disease__name"], r["count"]
        totals[code] = totals.get(code, 0) + n
        names.setdefault(code, []).append((n, name))
    rows = [
        {"disease": min(names[code], key=lambda p: (-p[0], p[1]))[1],
         "icd10_code": code,
         "count": total}
        for code, total in totals.items()
    ]
    rows.sort(key=lambda r: -r["count"])
    return rows[:limit]


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


# Coarsest last: a tier's index is how far up the gov hierarchy it sits.
_TIERS = [
    Jurisdiction.Level.LOCAL,
    Jurisdiction.Level.STATE,
    Jurisdiction.Level.NATIONAL,
]


def _tiers_for(jurisdiction, offered=_TIERS):
    """Which tier rollups a seat may be shown, its own being the coarsest.

    A Kano seat's rows folded to "national" would print under Nigeria as though
    it were the country's total, when it is only Kano's. So tiers above the
    seat's own are not offered at all: no number beats a number that is not the
    answer to the question its label asks.

    ``offered`` is the tiers that rollup publishes at all (not every one goes
    down to local). None narrows nothing — the platform admin sees the lot.
    """
    if jurisdiction is None:
        return offered
    cap = _TIERS.index(jurisdiction.level)
    return [t for t in offered if _TIERS.index(t) <= cap]


def platform_case_report_stats(start=None, end=None, jurisdiction=None):
    """Cross-tenant case-report rollup — the central collation.

    ``jurisdiction`` narrows it to one authority's patch; None is the national
    view.
    """
    reports = apply_range(
        _scoped(CaseReport, True, jurisdiction), start, end
    )
    stats = _case_breakdown(reports)
    stats["by_tenant"] = list(
        reports.values("tenant__name").annotate(count=Count("id")).order_by("-count")[:20]
    )
    # Cross-tenant collation keyed on ICD-10 (fixes name-collision double counting).
    stats["by_icd10"] = _normalized_diseases(reports)
    # Geographic rollup up the gov hierarchy: tenant → local → state → national,
    # stopping at the seat's own tier.
    for tier in _tiers_for(jurisdiction):
        stats[f"by_{tier}"] = _rollup_by_tier(reports, tier)
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


def report_sources(start=None, end=None, platform=False, jurisdiction=None):
    """Where reports originate — the source behind every collated number.

    Pools both report streams (case reports + adverse-drug reactions) and groups
    by who filed them and from where: reporter, region, and (platform) tenant.
    platform=True collates across all tenants via the unscoped manager.
    """
    cases = apply_range(_scoped(CaseReport, platform, jurisdiction), start, end)
    adrs = apply_range(
        _scoped(AdverseDrugReaction, platform, jurisdiction), start, end
    )

    out = {
        "total_cases": cases.count(),
        "total_adrs": adrs.count(),
        "by_region": _merge_counts(
            _grouped(cases, "region"), _grouped(adrs, "region"), "region"
        ),
        "by_region_state": _fold_region_to_state(
            _merge_counts(_grouped(cases, "region"), _grouped(adrs, "region"), "region")
        ),
        "by_reporter": _merge_counts(
            _grouped(cases, "reporter__username"),
            _grouped(adrs, "reporter__username"),
            "reporter__username",
        ),
    }
    if platform:
        out["by_tenant"] = _merge_counts(
            _grouped(cases, "tenant__name"),
            _grouped(adrs, "tenant__name"),
            "tenant__name",
        )
        # Roll the pooled stream up the gov hierarchy, stopping at the seat's tier.
        for tier in _tiers_for(jurisdiction):
            out[f"by_{tier}"] = _merge_tier(cases, adrs, tier)
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


def platform_stats(start=None, end=None, jurisdiction=None):
    """Cross-tenant dashboard (bypasses tenant scoping).

    ``jurisdiction`` narrows it to one authority's patch; None is the national
    view. The tenant and user counts narrow with it — a Kano seat is told how
    many facilities Kano has, not how many the country has.
    """
    events = apply_range(_scoped(AnalyticsEvent, True, jurisdiction), start, end)
    return {
        "total_tenants": _scope(
            Tenant.objects.all(), jurisdiction, field="jurisdiction"
        ).count(),
        "total_users": _scope(User.objects.all(), jurisdiction).count(),
        "total_searches": events.filter(event_type="search").count(),
        "content_gaps": _content_gaps(events),
        "searches_by_tenant": list(
            events.filter(event_type="search")
            .values("tenant__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        ),
        "search_trend": _series(events.filter(event_type="search"), days=90),
        "adverse_reactions": adr_stats(platform=True, jurisdiction=jurisdiction),
        **_prescribing_rollup(start, end, platform=True, jurisdiction=jurisdiction),
    }


def adr_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Adverse-drug-reaction rollup. platform=True collates across tenants."""
    reports = apply_range(
        _scoped(AdverseDrugReaction, platform, jurisdiction), start, end
    )

    out = {
        "total": reports.count(),
        "by_severity": _grouped(reports, "severity"),
        "by_outcome": _grouped(reports, "outcome"),
        "top_medications": list(
            reports.values("medication__generic_name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "top_reactions": list(
            reports.values("reaction").annotate(count=Count("id")).order_by("-count")[:10]
        ),
        "by_sex": _by_sex(reports),
        "trend": _series(reports, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name")
        for tier in _tiers_for(jurisdiction):
            out[f"by_{tier}"] = _rollup_by_tier(reports, tier)
    return out


def _scope(qs, jurisdiction, field="tenant__jurisdiction"):
    """Narrow a cross-tenant rollup to one jurisdiction and everything under it.

    A health authority reads its own patch: a Kano seat must not be answered
    with Lagos rows. ``None`` means no narrowing — the platform admin's national
    view. ``field`` is the path from the row to a jurisdiction, for the two
    rollups that count tenants and users rather than reports.
    """
    if jurisdiction is None:
        return qs
    return qs.filter(**{f"{field}__in": jurisdiction.subtree()})


def _scoped(model, platform, jurisdiction=None):
    """The rows one rollup may read — the one knob every platform rollup toggles.

    Tenant-scoped by default; ``platform`` swaps in the unscoped manager for a
    cross-tenant collation. all_objects bypasses tenant scoping, so on that
    path ``jurisdiction`` is the only thing narrowing what comes back.
    """
    if not platform:
        return model.objects.all()
    return _scope(model.all_objects.all(), jurisdiction)


def _grouped(qs, field, limit=None):
    rows = qs.values(field).annotate(count=Count("id")).order_by("-count")
    return list(rows[:limit] if limit else rows)


def _by_sex(qs):
    """Rows split by the patient's sex, the blank ones named for what they are.

    ``patient_sex`` is copied off the patient at save time; a row filed with no
    patient carries "". Printing that as an empty label reads as a bug, so it
    goes out as "unknown" — and stays in, because a sex breakdown that quietly
    drops the unrecorded share would overstate the split.
    """
    return [
        {"sex": r["patient_sex"] or "unknown", "count": r["count"]}
        for r in _grouped(qs, "patient_sex")
    ]


def lab_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Lab-result rollup incl. the antimicrobial-resistance (AMR) signal.

    AMR rate = resistant isolates / all isolates with a susceptibility result,
    sliced by organism and by antibiotic. platform=True collates across tenants.
    """
    reports = apply_range(_scoped(LabResult, platform, jurisdiction), start, end)
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
        "by_sex": _by_sex(reports),
        "isolates_tested": tested_n,
        "resistant": resistant.count(),
        "amr_rate": round(resistant.count() / tested_n, 4) if tested_n else None,
        "amr_by_organism": amr_by("organism"),
        "amr_by_antibiotic": amr_by("antibiotic"),
        "top_organisms": _grouped(reports.exclude(organism=""), "organism", 10),
        "by_region": _grouped(reports, "region"),
        "trend": _series(reports, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
    return out


def chw_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Community-health-worker field reports: out-of-facility care volume,
    danger signs and referral rate."""
    reports = apply_range(_scoped(CommunityHealthReport, platform, jurisdiction), start, end)
    total = reports.count()
    referred = reports.filter(referred=True).count()
    out = {
        "total": total,
        "danger_signs": reports.filter(danger_signs=True).count(),
        "referred": referred,
        "referral_rate": round(referred / total, 4) if total else None,
        "by_type": _grouped(reports, "report_type"),
        "by_sex": _by_sex(reports),
        "by_region_state": _fold_region_to_state(_grouped(reports, "region")),
        "trend": _series(reports, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
    return out


def facility_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Health-service KPIs averaged across facility snapshots: bed occupancy,
    waiting time, staffing and total throughput."""
    reports = apply_range(_scoped(FacilityMetric, platform, jurisdiction), start, end)
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
        "trend": _series(reports, days=90),
    }
    if platform:
        # Throughput per facility — who is busiest.
        out["by_tenant"] = list(
            reports.values("tenant__name")
            .annotate(count=Sum("patients_treated"))
            .order_by("-count")[:20]
        )
    return out


def insurance_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Insurance-claim rollup: volume, cost and approval rate by status &
    diagnosis."""
    claims = apply_range(_scoped(InsuranceClaim, platform, jurisdiction), start, end)
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
        "by_sex": _by_sex(claims),
        "top_diagnoses": list(
            claims.exclude(diagnosis=None)
            .values("diagnosis__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ),
        "by_region_state": _fold_region_to_state(_grouped(claims, "region")),
        "trend": _series(claims, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(claims, "tenant__name", 20)
    return out


def appointment_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Appointment utilization: in-person vs telemedicine split and no-show rate."""
    appts = apply_range(_scoped(Appointment, platform, jurisdiction), start, end)
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
        "by_sex": _by_sex(appts),
        "by_status": _grouped(appts, "status"),
        "trend": _series(appts, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(appts, "tenant__name", 20)
    return out


def _median_minutes(qs, start_field, end_field):
    """Median minutes between two datetime columns, or None with no rows.

    The database sorts and only the middle row (or the two straddling it) comes
    back, so the window can hold any number of rows without the whole span
    column being read into memory. Rows missing either end are not counted:
    they have no duration, and counting them as zero would flatter the number.
    """
    spans = (
        qs.exclude(**{f"{start_field}__isnull": True})
        .exclude(**{f"{end_field}__isnull": True})
        .annotate(
            span=ExpressionWrapper(
                F(end_field) - F(start_field), output_field=DurationField()
            )
        )
        .order_by("span")
        .values_list("span", flat=True)
    )
    count = spans.count()
    if not count:
        return None
    # One row for an odd count, the two either side of the middle for an even
    # one — the same rows statistics.median would have averaged.
    middle = spans[(count - 1) // 2:count // 2 + 1]
    return round(sum(s.total_seconds() for s in middle) / len(middle) / 60, 1)


def consultation_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Clinic load: what patients came with, and where they went next.

    ``by_disposition`` is over closed consultations only — an open note has no
    disposition yet, and counting those blanks would read as a fifth outcome.
    """
    rows = apply_range(_scoped(Consultation, platform, jurisdiction), start, end)
    closed = rows.filter(status=Consultation.Status.CLOSED)
    closed_count = closed.count()
    admitted = closed.filter(disposition=Consultation.Disposition.ADMITTED).count()
    # Minutes from opening the note to closing it — how long a visit takes.
    # Median, not mean: one note left open over a weekend would otherwise move
    # the whole number.
    out = {
        "total": rows.count(),
        "open": rows.filter(status=Consultation.Status.OPEN).count(),
        "admission_rate": (
            round(admitted / closed_count, 4) if closed_count else None
        ),
        "median_minutes_to_close": _median_minutes(
            closed, "created_at", "closed_at"
        ),
        "by_disposition": _grouped(closed, "disposition"),
        "by_age_group": _grouped(rows, "patient_age_group"),
        "by_sex": _by_sex(rows),
        "top_complaints": _grouped(rows, "chief_complaint", 20),
        # Signs and symptoms live on the case report the visit was filed
        # against; a consultation with no report (or one with no symptoms
        # ticked) has nothing to add here, so it is left out rather than
        # counted under a blank label.
        "top_symptoms": _grouped(
            rows.filter(case_report__symptoms__isnull=False),
            "case_report__symptoms__name", 20,
        ),
        "by_region": _grouped(rows, "region"),
        "trend": _series(rows, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(rows, "tenant__name", 20)
    return out


def immunization_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Vaccination coverage rollup: doses by vaccine, region and age band."""
    reports = apply_range(_scoped(Immunization, platform, jurisdiction), start, end)
    out = {
        "total_doses": reports.count(),
        "by_vaccine": _grouped(reports, "vaccine", 20),
        "by_age_group": _grouped(reports, "patient_age_group"),
        "by_sex": _by_sex(reports),
        "by_region": _grouped(reports, "region"),
        "by_region_state": _fold_region_to_state(_grouped(reports, "region")),
        "trend": _series(reports, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
        offered = [Jurisdiction.Level.STATE, Jurisdiction.Level.NATIONAL]
        for tier in _tiers_for(jurisdiction, offered):
            out[f"by_{tier}"] = _rollup_by_tier(reports, tier)
    return out


def vital_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Vital-registration rollup with maternal & infant mortality.

    Maternal mortality ratio = maternal deaths per 100 000 live births.
    Infant mortality rate     = infant deaths per 1 000 live births.
    Rates are None when there are no recorded births (no denominator).
    """
    events = apply_range(_scoped(VitalEvent, platform, jurisdiction), start, end)
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
        "deaths_by_sex": _by_sex(deaths),
        "by_region": _fold_region_to_state(_grouped(events, "region")),
        "birth_trend": _series(
            events.filter(event_type=VitalEvent.Kind.BIRTH), days=90
        ),
        "death_trend": _series(deaths, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(events, "tenant__name", 20)
        for tier in _tiers_for(jurisdiction, [Jurisdiction.Level.STATE]):
            out[f"by_{tier}"] = _rollup_by_tier(deaths, tier)
    return out


def stock_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Pharmacy stock & usage rollup: live shortages and consumption trends.

    ``shortages`` is the actionable list — medications flagged stocked-out, most
    recent first — so central can target resupply.
    """
    reports = apply_range(_scoped(StockReport, platform, jurisdiction), start, end)
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
        "trend": _series(reports, days=90),
    }
    if platform:
        out["by_tenant"] = _grouped(reports, "tenant__name", 20)
    return out


def prescription_stats(start=None, end=None, platform=False, jurisdiction=None):
    """Prescribing & dispensing rollup: what gets prescribed and whether the
    pharmacy actually hands it over.

    ``dispense_rate`` is over orders that were meant to be filled — cancelled
    ones are excluded, and a partial fill counts as dispensed.

    ``by_diagnosis`` and ``by_diagnosis_medication`` collate the orders under
    the diagnosis they were written for, so the report answers "what is
    prescribed for this condition", not just "what is prescribed".
    """
    rx = apply_range(_scoped(Prescription, platform, jurisdiction), start, end)
    fillable = rx.exclude(status=Prescription.Status.CANCELLED)
    dispensed = fillable.filter(status__in=_RX_FILLED).count()
    due = fillable.count()
    total = rx.count()
    linked = rx.exclude(case_report__disease=None).count()
    out = {
        "total": total,
        "dispensed": dispensed,
        "dispense_rate": round(dispensed / due, 4) if due else None,
        "top_medications": _grouped(rx, "medication__generic_name", 10),
        # Prescribing collated against the reason it was written for.
        # ``linked`` is the share of orders that carry a diagnosis at all:
        # below 1, the pair rows describe only part of the prescribing.
        "by_diagnosis": [
            {"diagnosis": r["case_report__disease__name"] or "—",
             "count": r["count"]}
            for r in _grouped(rx, "case_report__disease__name", 20)
        ],
        "by_diagnosis_medication": _diagnosis_pairs(rx),
        "linked": linked,
        "linked_rate": round(linked / total, 4) if total else None,
        "by_status": _grouped(rx, "status"),
        "by_sex": _by_sex(rx),
        "by_region": _grouped(rx, "region"),
    }
    if platform:
        out["by_tenant"] = _grouped(rx, "tenant__name", 20)
    return out


# Money buckets the state rollup publishes, with how many characters of the
# ISO date label each one keeps: 2026-09-09 / 2026-09 / 2026.
_SALES_PERIODS = (
    ("daily", TruncDate, 10),
    ("monthly", TruncMonth, 7),
    ("yearly", TruncYear, 4),
)


def _money_by_tier(sales, returns, trunc, width, level, juris):
    """Fold takings up to `level`, bucketed by period. One row per (area, period).

    Same fold as _rollup_by_tier — group in SQL by the tenant's own
    jurisdiction, walk each up to its ancestor in Python — with two streams
    instead of one: sales add, refunds subtract. A refund lands in the period
    it was recorded in, never the period of the sale it undoes, which is the
    rule the tenant's own reports keep (see apps/reports/views.py).
    """
    totals = {}
    for qs, sign, counts in ((sales, 1, True), (returns, -1, False)):
        rows = (
            qs.exclude(tenant__jurisdiction=None)
            .annotate(period=trunc("created_at", output_field=DateField()))
            .values("tenant__jurisdiction", "period")
            .annotate(amount=Sum("total" if counts else "amount"), n=Count("id"))
        )
        for r in rows:
            node = juris.get(r["tenant__jurisdiction"])
            anc = node.ancestor(level) if node else None
            if anc is None:
                continue
            key = (anc.name, str(r["period"])[:width])
            bucket = totals.setdefault(key, {"revenue": ZERO, "sales": 0})
            bucket["revenue"] += sign * (r["amount"] or ZERO)
            if counts:
                bucket["sales"] += r["n"]
    return [
        {level: area, "period": period, "revenue": v["revenue"], "sales": v["sales"]}
        for (area, period), v in sorted(totals.items())
    ]


def platform_sales_stats(start=None, end=None, jurisdiction=None):
    """What the counters took, per state, by day / month / year.

    The cross-tenant money view a health authority reads: totals for the patch
    it answers for, never a named patient or a single facility's takings.
    Revenue is net of refunds recorded in the same period, and counts only the
    statuses the tenant reports count (Sale.REVENUE_STATUSES) — a cancelled
    sale never happened and a credit sale has not been paid for.

    Folds to state, or to local government for a seat that answers for one:
    a local's rows printed under its state's name would read as the state's
    total (the same guard _tiers_for makes for the report rollups).
    """
    sales = apply_range(
        _scope(
            Sale.all_objects.filter(status__in=Sale.REVENUE_STATUSES), jurisdiction
        ),
        start, end,
    )
    returns = apply_range(
        _scope(
            ReturnRecord.all_objects.filter(sale__status__in=Sale.REVENUE_STATUSES),
            jurisdiction,
        ),
        start, end,
    )
    level = _tiers_for(
        jurisdiction, offered=[Jurisdiction.Level.LOCAL, Jurisdiction.Level.STATE]
    )[-1]
    juris = {j.id: j for j in Jurisdiction.objects.all()}
    stats = {"level": level}
    for key, trunc, width in _SALES_PERIODS:
        stats[key] = _money_by_tier(sales, returns, trunc, width, level, juris)
    return stats


def platform_controlled_stats(start=None, end=None, jurisdiction=None):
    """Controlled (poison) drugs prescribed, dispensed and sold, up to the state.

    The regulator's question about the poison register: how much of the
    controlled list was written for in this patch, how much of it was actually
    handed over against a script, and how much went over the counter with no
    script behind it at all. Everything counted in lines and in units, because
    "50 scripts" and "5,000 tablets" are different alarms.

    Prescribed is every script line for an item flagged ``is_controlled``;
    dispensed is the subset ticked off as handed over. ``otc`` is the till
    side: sale lines for a flagged item on a sale that names no prescription.
    Its units are net of returns, and a cancelled or fully returned sale is not
    counted at all — the register wants what left the shelf and stayed gone.

    ponytail: a script line typed in free text (``item`` blank) carries no flag
    and so is not counted — link the line to the shelf item to have it counted.
    """
    rx_counts = {
        "prescribed": Count("id"),
        "prescribed_units": Sum("quantity"),
        "dispensed": Count("id", filter=Q(is_dispensed=True)),
        "dispensed_units": Sum("quantity", filter=Q(is_dispensed=True)),
    }
    otc_counts = {
        "otc": Count("id"),
        "otc_units": Sum(F("quantity") - F("return_quantity")),
    }
    fields = (*rx_counts, *otc_counts)
    lines = apply_range(
        _scope(
            PrescriptionItem.all_objects.filter(item__is_controlled=True),
            jurisdiction,
        ),
        start, end,
    )
    # No script behind it: neither the dispensing prescription nor the older
    # analytics one. Either link means the sale is already on the script side.
    tills = apply_range(
        _scope(
            SaleItem.all_objects.filter(
                item__is_controlled=True,
                sale__status__in=Sale.REVENUE_STATUSES,
                sale__rx=None,
                sale__prescription=None,
            ),
            jurisdiction,
        ),
        start, end,
    )
    level = _tiers_for(
        jurisdiction, offered=[Jurisdiction.Level.LOCAL, Jurisdiction.Level.STATE]
    )[-1]
    juris = {j.id: j for j in Jurisdiction.objects.all()}

    def areas(qs, counts):
        rows = (
            qs.exclude(tenant__jurisdiction=None)
            .values("tenant__jurisdiction")
            .annotate(**counts)
        )
        for r in rows:
            node = juris.get(r["tenant__jurisdiction"])
            anc = node.ancestor(level) if node else None
            if anc is not None:
                yield anc.name, r

    def drugs(qs, counts):
        # Group both sides on the shelf item's name, not the line's copied one,
        # or a renamed item would land in two buckets.
        for r in qs.values(drug=F("item__name")).annotate(**counts):
            yield r["drug"], r

    def rollup(group):
        """One bucket per name, script columns and till columns side by side."""
        totals = {}
        for qs, counts in ((lines, rx_counts), (tills, otc_counts)):
            for name, row in group(qs, counts):
                bucket = totals.setdefault(name, dict.fromkeys(fields, 0))
                for field in counts:
                    bucket[field] += row[field] or 0
        return totals

    def busiest(totals):
        # Lines written plus lines sold: a drug that only ever goes over the
        # counter still belongs at the top of the list.
        return sorted(totals.items(), key=lambda kv: -(kv[1]["prescribed"]
                                                       + kv[1]["otc"]))

    by_area = [{level: area, **v} for area, v in busiest(rollup(areas))]
    # Which drugs, not just how many: a state acts on the molecule, not the total.
    by_drug = [{"drug": d, **v} for d, v in busiest(rollup(drugs))[:50]]
    return {"level": level, "by_area": by_area, "by_drug": by_drug}
