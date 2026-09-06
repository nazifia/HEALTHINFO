"""One rounding rule for every stored amount, shared by every app that keeps
money. Was copied into five models modules; one copy means one answer to
"how many kobo".
"""
from decimal import Decimal

MONEY = Decimal("0.01")


def money(value):
    """Round to kobo. Every stored amount goes through this."""
    return Decimal(value).quantize(MONEY)
