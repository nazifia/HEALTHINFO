"""Region = "LGA, State" from the Nigeria list: validated on write, rolled up
to state in the breakdown, and the same list everywhere it is offered."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

from apps.analytics.models import CaseReport
from apps.analytics.nigeria import region_state, valid_regions
from apps.analytics.serializers import CaseReportSerializer
from apps.analytics.stats import case_report_stats
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def test_region_state_parses_lga_state():
    assert region_state("Ikeja, Lagos") == "Lagos"
    assert region_state("garbage") == ""


def test_known_regions_validate_and_typos_reject():
    assert "Ikeja, Lagos" in valid_regions()
    assert CaseReportSerializer().validate_region("Ikeja, Lagos") == "Ikeja, Lagos"
    assert CaseReportSerializer().validate_region("") == ""  # optional
    with pytest.raises(Exception):
        CaseReportSerializer().validate_region("Nowhere, Atlantis")


def test_breakdown_rolls_region_up_to_state(tenant):
    CaseReport.objects.create(severity="mild", region="Ikeja, Lagos")
    CaseReport.objects.create(severity="mild", region="Epe, Lagos")
    CaseReport.objects.create(severity="mild", region="Bende, Abia")
    by_state = {r["state"]: r["count"] for r in case_report_stats()["by_region_state"]}
    assert by_state == {"Lagos": 2, "Abia": 1}


ROOT = Path(__file__).resolve().parent.parent


def _generated():
    """scripts/gen_nigeria.py, loaded without running it."""
    spec = importlib.util.spec_from_file_location(
        "gen_nigeria", ROOT / "scripts" / "gen_nigeria.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Three places offer or check a region: the Jurisdiction tree the web picker
# reads, the JSON the serializer validates against, and the Dart constant the
# Flutter picker shows. They were hand-maintained and drifted — mobile offered
# "Gayuk, Adamawa" for a server that only accepted "Guyuk, Adamawa", so those
# reports could not be filed at all. Now two of the three are generated from
# the first, and these fail the build when a regenerate was forgotten.


def test_validator_json_matches_the_source_list():
    gen = _generated()
    stored = json.loads(gen.JSON_PATH.read_text(encoding="utf-8"))
    assert stored == json.loads(gen.json_source()), (
        "apps/analytics/nigeria_states.json is stale — run scripts/gen_nigeria.py"
    )


def test_flutter_picker_matches_the_source_list():
    gen = _generated()
    assert gen.DART_PATH.read_text(encoding="utf-8") == gen.dart_source(), (
        "mobile/lib/nigeria_data.dart is stale — run scripts/gen_nigeria.py"
    )


def test_no_second_copy_of_the_list_in_the_flutter_app():
    # The picker re-exports the generated constant; it must not declare its own.
    picker = (ROOT / "mobile" / "lib" / "nigeria.dart").read_text(encoding="utf-8")
    assert "nigeriaStates = {" not in picker


def test_every_region_the_pickers_offer_is_one_the_server_accepts():
    gen = _generated()
    dart = gen.DART_PATH.read_text(encoding="utf-8")
    offered = set()
    for state, body in re.findall(r"^  '([^']+)': \[(.*)\],$", dart, re.M):
        for single, double in re.findall(r"'([^']*)'|\"([^\"]*)\"", body):
            offered.add("%s, %s" % (single or double, state))
    assert len(offered) == 774
    assert offered <= valid_regions()


def _migration():
    """The 0018 data migration, loaded by path (its name starts with a digit)."""
    spec = importlib.util.spec_from_file_location(
        "mig0018",
        ROOT / "apps" / "analytics" / "migrations"
        / "0018_canonical_region_spellings.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_rename_target_is_a_region_the_server_accepts():
    mig = _migration()
    assert set(mig.RENAMES.values()) <= valid_regions()
    # A source that is already valid would be a rewrite of a good value.
    assert not set(mig.RENAMES) & valid_regions()


def test_migration_rewrites_the_old_picker_spellings(tenant):
    from django.apps import apps as django_apps

    mig = _migration()
    stale = CaseReport.objects.create(severity="mild", region="Gayuk, Adamawa")
    fct = CaseReport.objects.create(severity="mild", region="Bwari, FCT - Abuja")
    good = CaseReport.objects.create(severity="mild", region="Ikeja, Lagos")
    blank = CaseReport.objects.create(severity="mild", region="")

    mig.canonicalise(django_apps, None)

    for row in (stale, fct, good, blank):
        row.refresh_from_db()
    assert stale.region == "Guyuk, Adamawa"
    assert fct.region == "Bwari, Federal Capital Territory"
    # A region that was already right, and one never filled in, are left alone.
    assert good.region == "Ikeja, Lagos"
    assert blank.region == ""
    # And what it wrote is what the serializer now accepts.
    assert CaseReportSerializer().validate_region(stale.region) == stale.region


def test_migration_covers_every_model_holding_a_region():
    """A new model with a region must be added to the migration's list."""
    from django.apps import apps as django_apps

    mig = _migration()
    listed = set(mig.REGION_MODELS)
    holders = {
        (m._meta.app_label, m.__name__)
        for m in django_apps.get_models()
        if any(f.name == "region" for f in m._meta.get_fields())
    }
    assert holders <= listed, "region field on a model the migration skips"
