"""The receipt as raw ESC/POS bytes, for a thermal printer fed directly.

The HTML receipt prints through a browser; this is for the printer with no
browser in front of it — a network printer on port 9100, a USB printer behind
a tiny local agent, or a Bluetooth one driven from the phone. Plain text and
the handful of ESC/POS commands every 58/80mm printer honours; no bitmap, so
the logo stays on the HTML version.

ponytail: hand-rolled rather than python-escpos, which needs Pillow and a USB
stack for the six commands used here. Reach for it when someone wants the
logo or a barcode on the roll.
"""

from django.utils import timezone

ESC, GS = b"\x1b", b"\x1d"
INIT = ESC + b"@"
ALIGN_LEFT, ALIGN_CENTRE = ESC + b"a\x00", ESC + b"a\x01"
BOLD_ON, BOLD_OFF = ESC + b"E\x01", ESC + b"E\x00"
DOUBLE_ON, DOUBLE_OFF = GS + b"!\x11", GS + b"!\x00"
# Feed past the blade, then partial cut. Printers without a cutter ignore it.
CUT = b"\n\n\n" + GS + b"V\x01"

# Characters per line at the default font: 80mm rolls fit 48, 58mm fit 32.
COLUMNS = {80: 48, 58: 32}


def _row(left, right, width):
    """``left`` and ``right`` on one line, right-aligned; clips left to fit."""
    left = str(left)[: width - len(right) - 1]
    return f"{left:<{width - len(right)}}{right}\n"


def render(sale, lines, tenant, paper=80):
    """The receipt for ``sale`` as bytes ready to write to the printer."""
    width = COLUMNS.get(paper, COLUMNS[80])
    row = lambda left, right="": _row(left, str(right), width)  # noqa: E731
    rule = "-" * width + "\n"
    out = bytearray(INIT)

    def text(s):
        # CP437 is the one code page every printer ships with; the naira sign
        # and anything else outside it become "?" rather than garbage.
        out.extend(s.encode("cp437", "replace"))

    out += ALIGN_CENTRE + DOUBLE_ON + BOLD_ON
    text((tenant.name or "Pharmacy") + "\n")
    out += DOUBLE_OFF + BOLD_OFF
    for line in (tenant.address, tenant.contact):
        if line:
            text(line + "\n")
    if sale.status == "cancelled":
        out += BOLD_ON
        text("*** CANCELLED ***\n")
        out += BOLD_OFF
    out += ALIGN_LEFT
    text(rule)

    text(row("Receipt", sale.reference))
    text(row("Date", timezone.localtime(sale.created_at).strftime("%Y-%m-%d %H:%M")))
    if sale.patient:
        text(row("Patient", sale.patient.full_name))
        text(row("Hospital no.", sale.patient.hospital_number))
    if sale.enrollment:
        text(row("Scheme", sale.enrollment.hmo.name))
        text(row("Member no.", sale.enrollment.member_number))
    served = sale.served_by
    text(row("Served by", (served and (served.username or served.phone)) or "-"))
    text(rule)

    for line in lines:
        text(line.item.name[:width] + "\n")
        detail = f"  {line.quantity} x {line.unit_price}"
        if line.batch:
            detail += f"  [{line.batch.batch_number}]"
        text(row(detail, line.line_total))
    if not lines:
        text("No items.\n")
    text(rule)

    text(row("Subtotal", sale.subtotal))
    if sale.discount:
        text(row("Discount", f"-{sale.discount}"))
    out += BOLD_ON
    text(row("TOTAL", sale.total))
    out += BOLD_OFF
    if sale.hmo_payable:
        text(row(f"Covered by {sale.enrollment.hmo.name if sale.enrollment else 'scheme'}",
                 sale.hmo_payable))
        text(row("Patient pays", sale.patient_payable))
    text(row(f"Paid ({sale.get_payment_method_display()})", sale.amount_paid))
    if sale.change_due:
        text(row("Tendered", sale.amount_tendered))
        text(row("Change", sale.change_due))
    text(row("Balance", sale.balance_due))
    text(rule)

    out += ALIGN_CENTRE
    text("Goods dispensed are checked before\nleaving the counter. Thank you.\n")
    out += CUT
    return bytes(out)
