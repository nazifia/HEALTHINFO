"""Mirror what a facility actually did into the data centre.

A hospital diagnoses; a pharmacy hands the drugs over. Both happen in the
operational apps — ``apps.prescriptions`` at the counter, ``apps.pos`` at the
till — and neither reached ``apps.analytics``, which is the store every tenant
dashboard and the central (platform + IDSR) collation read from. A facility
could dispense all year and the centre would know nothing unless somebody
re-typed the day's work as a report.

This module captures the two facts worth collating — **the diagnosis** and
**the medications used** — as they happen, for hospitals and pharmacies alike.
A pharmacy's counter feeds it on a signal, as a script is written and as its
drugs go out; a hospital's clinician feeds it from the visit, where the
diagnosis they reach is filed as they reach it (``capture_consultation``, wired
to the consultation's ``diagnose`` action).

There is no second store to ship to. A captured row is tenant-scoped like every
other analytics row: the tenant's own dashboard reads it through ``objects``,
and central pools it across every tenant through ``all_objects``, up the
jurisdiction chain. Capturing once puts it in both.

Every captured row carries a ``source_ref`` naming the operational row behind
it, so the same dispense arriving twice — a retry, or one script filled through
both the counter tick and a till sale — updates one row instead of inflating
the counts.
"""
import re

from django.db.models import Q

from apps.catalog.models import Disease, Medication
from apps.prescriptions.models import PrescriptionItem

from .models import CaseReport, Prescription


def _catalog(model, tenant_id):
    """A tenant's own catalog rows plus the shared global ones.

    Filtered explicitly rather than through the shared manager: capture runs
    from a signal, where the thread-local current tenant is not guaranteed to
    be the tenant whose counter this row came off.
    """
    return model.all_objects.filter(Q(tenant_id=tenant_id) | Q(tenant__isnull=True))


def medication_for(tenant_id, item=None, name=""):
    """The catalog drug behind a stocked item, or None when it isn't a drug.

    Gloves, sachets of water and biscuits cross the same counter; only what
    matches the drug catalog belongs in a surveillance store.
    """
    if item is not None and item.medication_id:
        return item.medication
    name = (name or (item.name if item is not None else "")).strip()
    if not name:
        return None
    meds = _catalog(Medication, tenant_id)
    # "Amoxicillin 250mg" on the shelf is "Amoxicillin" in the catalog: try the
    # label whole, then its first word. ponytail: two indexed lookups, not a
    # scan of the catalog per dispense. Fill StockItem.medication for the rest.
    return (
        meds.filter(Q(generic_name__iexact=name) | Q(brand_name__iexact=name)).first()
        or meds.filter(generic_name__iexact=name.split()[0]).first()
    )


def disease_for(tenant_id, text):
    """The catalog disease a free-text diagnosis names, or None.

    None is not a failure — the case is still filed with the text in its notes,
    so an unmatched diagnosis is never a case the centre never heard about.
    """
    text = (text or "").strip()
    if not text:
        return None
    head = text.split(",")[0].strip()  # "Malaria, uncomplicated" -> "Malaria"
    return _catalog(Disease, tenant_id).filter(
        Q(icd10_code__iexact=head) | Q(name__iexact=head) | Q(name__iexact=text)
    ).first()


def _duration_days(text):
    """Days out of a written duration ("5 days", "5/7"), or None."""
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


def _region(patient):
    return patient.region if patient is not None else ""


def capture_diagnosis(rx):
    """File the diagnosis written on a counter script as a case report.

    Returns the CaseReport, or None when the script carries no diagnosis: a
    repeat purchase with nothing written on it is not a case. Idempotent — one
    case per script, however many lines are filled off it.
    """
    text = (rx.diagnosis or "").strip()
    if not text:
        return None
    case, _created = CaseReport.all_objects.get_or_create(
        tenant_id=rx.tenant_id, source_ref=f"rx:{rx.pk}",
        defaults={
            "disease": disease_for(rx.tenant_id, text),
            "patient": rx.patient,
            "reporter": rx.created_by,
            "region": _region(rx.patient),
            "notes": text,
        },
    )
    return case


def mark_dispensed(order):
    """Move an order already on file to dispensed. Its save stamps the time."""
    if order.status != Prescription.Status.DISPENSED:
        order.status = Prescription.Status.DISPENSED
        order.save(update_fields=["status", "dispensed_at", "updated_at"])
    return order


def capture_medication(*, tenant_id, medication, source_ref, patient=None,
                       case_report=None, reporter=None, dose="",
                       duration_days=None, notes="",
                       status=Prescription.Status.DISPENSED):
    """Record one drug ordered or handed over. Idempotent per source.

    ``status`` is what the operational row says now: a script line written but
    not yet filled is ``PRESCRIBED``, and the same line reaching the counter is
    ``DISPENSED``. The move only ever runs forward — a row already dispensed is
    never walked back to prescribed by a later save of the line it came from.

    A unique (tenant, source_ref) constraint backs the get_or_create, so two
    concurrent dispenses of one line cannot race a second row past it: the
    loser raises IntegrityError, which the signal logs and drops — the row it
    was going to write is already there.
    """
    order, created = Prescription.all_objects.get_or_create(
        tenant_id=tenant_id, source_ref=source_ref,
        defaults={
            "medication": medication,
            "patient": patient,
            "case_report": case_report,
            "reporter": reporter,
            "dose": dose,
            "duration_days": duration_days,
            "notes": notes,
            "region": _region(patient),
            "status": status,
        },
    )
    if created or status != Prescription.Status.DISPENSED:
        return order
    return mark_dispensed(order)


def capture_prescription_line(line, *, user=None, dispensed=None):
    """A drug on a counter script: its diagnosis, its drug, and where it got to.

    Filed when the line is written, not only when it is ticked off. A patient
    who was prescribed a drug the shelf did not have is the stockout the centre
    is looking for, and a line that never reaches the counter would otherwise
    leave no trace of having been ordered at all.

    ``dispensed`` overrides the line's own tick for the route that sells a
    script's drug at the till without ticking the line off: the drug left the
    shelf, whatever the counter copy of the script still says.
    """
    rx = line.prescription
    tenant_id = line.tenant_id or rx.tenant_id
    medication = medication_for(tenant_id, line.item, line.name)
    if medication is None:
        return None
    return capture_medication(
        tenant_id=tenant_id, medication=medication,
        source_ref=f"rxline:{line.pk}", patient=rx.patient,
        case_report=capture_diagnosis(rx),
        reporter=line.dispensed_by or user or rx.created_by,
        dose=line.dosage, duration_days=_duration_days(line.duration),
        notes=line.instructions,
        status=(Prescription.Status.DISPENSED
                if (line.is_dispensed if dispensed is None else dispensed)
                else Prescription.Status.PRESCRIBED),
    )


def capture_consultation(consultation, diagnosis, *, reporter=None, severity=""):
    """File the diagnosis a clinician reached on a visit as a case report.

    The hospital's half of what the counter already does: free text in, a
    catalog disease matched out, and the written text kept in ``notes`` when
    nothing matches — an unmatched diagnosis is still a case the centre hears
    about.

    One visit is one case. A case already linked to the consultation is this
    visit's diagnosis however it got there — a client that filed one itself
    included — so re-diagnosing corrects that case rather than filing a second
    one the rollups would count as a second patient. ``severity`` sets the
    severity of a case filed here; a case that already exists keeps the
    severity whoever filed it recorded.
    """
    text = (diagnosis or "").strip()
    if not text:
        return None
    tenant_id = consultation.tenant_id
    case = consultation.case_report
    if case is None:
        defaults = {
            "disease": disease_for(tenant_id, text),
            "patient": consultation.patient,
            "patient_age_group": consultation.patient_age_group,
            "patient_sex": consultation.patient_sex,
            "reporter": reporter or consultation.reporter,
            "region": consultation.region or _region(consultation.patient),
            "notes": text,
        }
        if severity:
            defaults["severity"] = severity
        case, created = CaseReport.all_objects.get_or_create(
            tenant_id=tenant_id, source_ref=f"consult:{consultation.pk}",
            defaults=defaults,
        )
        if created:
            return case
    if case.notes != text:
        case.disease = disease_for(tenant_id, text)
        case.notes = text
        case.save(update_fields=["disease", "notes", "updated_at"])
    return case


def _rx_line_for(sale, item_id):
    """The script line a sold item is filling, when the sale came off a script."""
    if not (sale.rx_id and item_id):
        return None
    return PrescriptionItem.all_objects.filter(
        prescription_id=sale.rx_id, item_id=item_id
    ).first()


def capture_dispense(log):
    """One item handed over at a till — a hospital's pharmacy or a shop's counter.

    The till is the one place every dispense passes through, whichever route
    reached it: a walk-in sale, a script filled at the counter, or a hospital
    order its own clinician wrote.
    """
    sale = log.sale
    if sale is None:
        return None
    # A hospital clinician already wrote this order into the data centre. Fill
    # that row in rather than filing the same drug a second time.
    if sale.prescription_id:
        return mark_dispensed(sale.prescription)
    tenant_id = log.tenant_id or sale.tenant_id
    medication = medication_for(tenant_id, log.item, log.name)
    if medication is None:
        return None
    line = _rx_line_for(sale, log.item_id)
    if line is not None:
        # Same drug, same script: both routes key on the line, so ticking it off
        # at the counter and selling it at the till collapse onto one row.
        return capture_prescription_line(line, user=log.user, dispensed=True)
    return capture_medication(
        tenant_id=tenant_id, medication=medication,
        source_ref=f"dispense:{log.pk}", patient=sale.patient,
        case_report=capture_diagnosis(sale.rx) if sale.rx_id else None,
        reporter=log.user or sale.served_by,
    )
