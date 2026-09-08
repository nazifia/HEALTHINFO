"""Surveillance, differential, interaction-check, collation, ADR — new features."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User

from apps.analytics.models import AdverseDrugReaction, CaseReport
from apps.analytics.stats import adr_stats, platform_case_report_stats
from apps.analytics.surveillance import detect_spikes
from apps.catalog.models import Disease, DrugInteraction, Medication, Symptom
from apps.catalog.views import DifferentialView, InteractionCheckView
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def _auth_post(view, path, payload, tenant):
    """Build an authenticated, tenant-bound POST through a DRF APIView."""
    user = User.objects.create_user(
        phone="08030000000", password="x", tenant=tenant, role=Role.DOCTOR
    )
    req = APIRequestFactory().post(path, payload, format="json")
    req.tenant = tenant
    force_authenticate(req, user=user)
    return view.as_view()(req)


def _backdate(report, days_ago):
    when = timezone.now() - timedelta(days=days_ago)
    CaseReport.all_objects.filter(pk=report.pk).update(created_at=when)


def test_spike_detection_flags_latest_day_surge(tenant):
    flu = Disease.objects.create(name="Flu", slug="flu", icd10_code="J10")
    # Quiet baseline: 1 case/day for 4 prior days.
    for d in range(4):
        r = CaseReport.objects.create(disease=flu)
        _backdate(r, days_ago=1 + d)  # days 1..4 ago
    # Today: a surge of 8.
    for _ in range(8):
        CaseReport.objects.create(disease=flu)  # now

    alerts = detect_spikes(CaseReport.objects.all(), days=30)
    assert len(alerts) == 1
    assert alerts[0]["icd10_code"] == "J10"
    assert alerts[0]["current_day"] == 8


def test_quiet_days_count_as_zero_in_the_baseline(tenant):
    """A gap is a zero, not a missing bucket.

    Two busy days a fortnight back and nothing since: counting only the days
    that had cases puts the baseline at 6/day and hides today's cluster.
    """
    lassa = Disease.objects.create(name="Lassa", slug="lassa", icd10_code="A96")
    for days_ago in (15, 20):
        for _ in range(6):
            _backdate(CaseReport.objects.create(disease=lassa), days_ago=days_ago)
    for _ in range(5):
        CaseReport.objects.create(disease=lassa)  # today

    [alert] = detect_spikes(CaseReport.objects.all(), days=30)
    assert alert["current_day"] == 5
    assert alert["baseline_mean"] < 1  # 12 cases spread over 29 days, not 2
    assert len(alert["daily_counts"]) == 30


def test_no_spike_when_flat(tenant):
    cold = Disease.objects.create(name="Cold", slug="cold")
    for d in range(5):
        r = CaseReport.objects.create(disease=cold)
        _backdate(r, days_ago=d)
    assert detect_spikes(CaseReport.objects.all(), days=30) == []


def test_differential_ranks_by_symptom_overlap(tenant):
    fever = Symptom.objects.create(name="fever")
    cough = Symptom.objects.create(name="cough")
    flu = Disease.objects.create(name="Flu", slug="flu", status="published")
    flu.symptoms.set([fever, cough])
    cold = Disease.objects.create(name="Cold", slug="cold", status="published")
    cold.symptoms.set([cough])

    resp = _auth_post(
        DifferentialView, "/api/differential/",
        {"symptom_ids": [fever.id, cough.id]}, tenant,
    )
    names = [r["name"] for r in resp.data["results"]]
    assert names == ["Flu", "Cold"]  # Flu matches 2, Cold matches 1
    assert resp.data["results"][0]["matched"] == 2


def test_interaction_check_finds_pair_either_order(tenant):
    warfarin = Medication.objects.create(generic_name="warfarin")
    aspirin = Medication.objects.create(generic_name="aspirin")
    ibuprofen = Medication.objects.create(generic_name="ibuprofen")
    DrugInteraction.objects.create(
        medication_a=warfarin, medication_b=aspirin, severity="major"
    )

    resp = _auth_post(
        InteractionCheckView, "/api/interactions/check/",
        {"medication_ids": [aspirin.id, warfarin.id, ibuprofen.id]}, tenant,
    )
    assert len(resp.data["interactions"]) == 1
    assert resp.data["interactions"][0]["severity"] == "major"


def test_platform_collation_keys_on_icd10(db):
    a = Tenant.objects.create(name="A", slug="a")
    b = Tenant.objects.create(name="B", slug="b")
    # Same disease, different free-text names, same ICD-10 code across tenants.
    set_current_tenant(a)
    d1 = Disease.objects.create(name="Type 2 diabetes", slug="t2d", icd10_code="E11")
    CaseReport.objects.create(disease=d1)
    set_current_tenant(b)
    d2 = Disease.objects.create(name="T2DM", slug="t2dm", icd10_code="E11")
    CaseReport.objects.create(disease=d2)
    CaseReport.objects.create(disease=d2)

    c = Tenant.objects.create(name="C", slug="c")
    set_current_tenant(c)
    d3 = Disease.objects.create(name="AAA diabetes", slug="aaa", icd10_code="E11")
    CaseReport.objects.create(disease=d3)

    clear_current_tenant()
    rows = platform_case_report_stats()["by_icd10"]
    assert {r["icd10_code"]: r["count"] for r in rows} == {"E11": 4}  # collated despite name mismatch
    # One row, so one name stands for every spelling: the one most cases were
    # filed under. "AAA diabetes" sorts first and would win a tiebreak, but it
    # was written once against T2DM's two, so the modal spelling takes it.
    assert rows[0]["disease"] == "T2DM"


def test_adr_stats_rollup(tenant):
    drug = Medication.objects.create(generic_name="penicillin")
    AdverseDrugReaction.objects.create(
        medication=drug, reaction="anaphylaxis", severity="severe"
    )
    AdverseDrugReaction.objects.create(
        medication=drug, reaction="rash", severity="mild"
    )
    stats = adr_stats()
    assert stats["total"] == 2
    assert stats["top_medications"][0]["medication__generic_name"] == "penicillin"
