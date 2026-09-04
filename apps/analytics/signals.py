"""Capture operational dispensing into the data centre as it happens.

On signals rather than in the views because a drug leaves the shelf down
several routes — a till sale, a payment request a cashier completes, a script
ticked off at the counter — and every one of them owes the centre the same
record. Best-effort like the rest of analytics: a capture that fails must never
fail the sale a patient is standing at the counter for, so it is logged and the
dispensing carries on.
"""
import logging

from django.db.models.signals import post_save

from .capture import capture_dispense, capture_prescription_line

logger = logging.getLogger(__name__)


def _safely(fn, row):
    try:
        fn(row)
    except Exception:  # surveillance must never break dispensing
        logger.exception("Data-centre capture failed for %r", row)


def _on_dispensed(sender, instance, created, **kwargs):
    if created:
        _safely(capture_dispense, instance)


def _on_rx_line(sender, instance, **kwargs):
    # Fires on every save of a line; only a dispensed one is a fact to report.
    if instance.is_dispensed:
        _safely(capture_prescription_line, instance)


def connect():
    from apps.pos.models import DispensingLog
    from apps.prescriptions.models import PrescriptionItem

    post_save.connect(_on_dispensed, sender=DispensingLog,
                      dispatch_uid="analytics.capture_dispense")
    post_save.connect(_on_rx_line, sender=PrescriptionItem,
                      dispatch_uid="analytics.capture_rx_line")
