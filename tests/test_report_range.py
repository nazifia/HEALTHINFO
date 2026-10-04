"""Trading reports accept ?year=[&month=] as well as from/to and period."""
from datetime import date
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.reports.views import _resolve_range


def _r(**q):
    return _resolve_range(SimpleNamespace(query_params=q))


def test_month_and_year():
    assert _r(year="2024", month="2") == ("month", date(2024, 2, 1), date(2024, 2, 29))
    assert _r(year="2024") == ("year", date(2024, 1, 1), date(2024, 12, 31))


def test_from_to_wins_and_bad_month_rejected():
    assert _r(**{"from": "2024-01-01", "to": "2024-01-05", "year": "2020"})[0] == "custom"
    with pytest.raises(ValidationError):
        _r(year="2024", month="13")
