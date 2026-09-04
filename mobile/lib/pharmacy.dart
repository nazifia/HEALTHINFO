import 'package:intl/intl.dart';

/// Pharmacy rules the screens share: who may do what, how a basket adds up,
/// and the body the counter posts. Kept out of the widgets so the arithmetic
/// can be tested without pumping a frame — and so the role split can't drift
/// between screens.
///
/// Mirrors apps/accounts/permissions.py: the pharmacy admin (tenant admin, or
/// super admin) owns anything that rewrites what money is owed — prices, stock
/// corrections, claim decisions — and staff do the counter work.
const pharmacyAdminRoles = {'super_admin', 'tenant_admin'};
const pharmacyStaffRoles = {...pharmacyAdminRoles, 'pharmacist'};

bool isPharmacyAdmin(String? role) => pharmacyAdminRoles.contains(role);
bool isPharmacyStaff(String? role) => pharmacyStaffRoles.contains(role);

final _money = NumberFormat('#,##0.00');

/// Naira, thousands-separated, always two decimals. Accepts the strings DRF
/// sends for a DecimalField as well as numbers.
String money(Object? value) {
  final n = value is num ? value : num.tryParse('${value ?? ''}');
  return n == null ? '—' : '₦${_money.format(n)}';
}

/// A whole number for a KPI tile (units, counts) — null-safe.
String units(Object? value) {
  final n = value is num ? value : num.tryParse('${value ?? ''}');
  return n == null ? '—' : NumberFormat('#,##0').format(n);
}

/// One line the counter has added but not yet dispensed.
///
/// Only the item, quantity and any discount are the client's business — the
/// server picks the batches (first expiry first out) and prices the sale, so a
/// basket total here is an estimate to show the patient, never the invoice.
class BasketLine {
  final int itemId;
  final String name;
  final double unitPrice;
  final int quantity;
  final double discount;

  const BasketLine({
    required this.itemId,
    required this.name,
    required this.unitPrice,
    required this.quantity,
    this.discount = 0,
  });

  /// Never negative: a discount bigger than the line is a free line, not a
  /// refund the rest of the basket has to fund.
  double get lineTotal {
    final gross = unitPrice * quantity - discount;
    return gross < 0 ? 0 : gross;
  }
}

double basketTotal(List<BasketLine> lines) =>
    lines.fold(0, (sum, l) => sum + l.lineTotal);

/// POST body for /api/pharmacy/sales/.
///
/// Omits what the server owns: no totals, no batch choice. An HMO sale carries
/// the membership; every other method must not, and the API rejects it if it
/// does — so the caller's payment method decides whether the card travels.
Map<String, dynamic> saleBody({
  required List<BasketLine> lines,
  required String paymentMethod,
  int? patientId,
  int? enrollmentId,
}) {
  final insured = paymentMethod == 'hmo';
  return {
    'payment_method': paymentMethod,
    'patient': ?patientId,
    if (insured && enrollmentId != null) 'enrollment': enrollmentId,
    'items': [
      for (final l in lines)
        {
          'item': l.itemId,
          'quantity': l.quantity,
          if (l.discount > 0) 'discount': l.discount.toStringAsFixed(2),
        },
    ],
  };
}

/// Actions offered on a claim in its current state, mirroring the transitions
/// the API allows (apps/pharmacy/models.py Claim._ALLOWED). Staff send a claim;
/// only the admin decides or banks one.
List<String> claimActions(String? status, String? role) {
  if (!isPharmacyStaff(role)) return const [];
  final admin = isPharmacyAdmin(role);
  switch (status) {
    case 'draft':
    case 'rejected':
      return const ['submit'];
    case 'submitted':
      return admin ? const ['approve', 'reject'] : const [];
    case 'approved':
      return admin ? const ['pay'] : const [];
    default: // paid, cancelled — nothing left to do
      return const [];
  }
}

/// Same idea for a claim batch (ClaimBatch's transitions).
List<String> batchActions(String? status, String? role) {
  if (!isPharmacyStaff(role)) return const [];
  final admin = isPharmacyAdmin(role);
  switch (status) {
    case 'draft':
      return const ['add-claims', 'submit', 'cancel'];
    case 'submitted':
      return admin ? const ['approve', 'pay', 'cancel'] : const ['cancel'];
    case 'approved':
      return admin ? const ['pay', 'cancel'] : const ['cancel'];
    default: // paid, cancelled
      return const [];
  }
}

/// Actions on a purchase order in its current state (PurchaseOrder.submit /
/// cancel in apps/pharmacy/models.py). Receiving is not here: it is offered per
/// line, for as long as anything on the order is still outstanding.
List<String> orderActions(String? status, String? role) {
  if (!isPharmacyStaff(role)) return const [];
  switch (status) {
    case 'draft':
      return const ['submit', 'cancel'];
    case 'submitted':
    case 'partial':
      // Cancelling here abandons what has not arrived; stock already received
      // stays received.
      return const ['cancel'];
    default: // received, cancelled
      return const [];
  }
}

/// One line being drafted onto an order — what to ask the supplier for.
class OrderLineDraft {
  final int itemId;
  final String name;
  final int quantity;
  final double unitCost;

  const OrderLineDraft({
    required this.itemId,
    required this.name,
    required this.quantity,
    required this.unitCost,
  });

  double get lineCost => quantity * unitCost;
}

double orderTotal(List<OrderLineDraft> lines) =>
    lines.fold(0, (sum, l) => sum + l.lineCost);

/// POST body for /api/pharmacy/purchase-orders/.
///
/// Lines travel under `items`; the API replaces the order's lines with them and
/// keeps `quantity_received` for itself, since what arrived is a fact about
/// deliveries, not something an order can assert.
Map<String, dynamic> purchaseOrderBody({
  required int supplierId,
  required List<OrderLineDraft> lines,
  String? expectedDate,
  String notes = '',
}) {
  return {
    'supplier': supplierId,
    'expected_date': ?expectedDate,
    if (notes.trim().isNotEmpty) 'notes': notes.trim(),
    'items': [
      for (final l in lines)
        {
          'item': l.itemId,
          'quantity_ordered': l.quantity,
          'unit_cost': l.unitCost.toStringAsFixed(2),
        },
    ],
  };
}

// ── Prescriptions ────────────────────────────────────────────────────────

/// Actions offered on a script in its current state (apps/prescriptions/views
/// PrescriptionViewSet). Dispensing is per line, so "dispense" here means the
/// whole of what is still open.
List<String> rxActions(String? status, String? role) {
  if (!isPharmacyStaff(role)) return const [];
  switch (status) {
    case 'pending':
    case 'partial':
      return const ['dispense', 'cancel'];
    default: // dispensed, cancelled — nothing left to hand over
      return const [];
  }
}

/// POST body for /api/prescriptions/scripts/.
///
/// The consultation fee is not sent: the server snapshots it from the
/// prescriber's own band, so a client that named a figure could undercharge
/// for a consultation the doctor prices.
Map<String, dynamic> prescriptionBody({
  required String customerName,
  required List<RxLineDraft> lines,
  String customerPhone = '',
  int? prescriberId,
  int? customerId,
  int? patientId,
  String doctorName = '',
  String diagnosis = '',
  String consultationCategory = '',
}) {
  return {
    'customer_name': customerName.trim().isEmpty
        ? 'Walk-in'
        : customerName.trim(),
    if (customerPhone.trim().isNotEmpty) 'customer_phone': customerPhone.trim(),
    'prescriber': ?prescriberId,
    'customer': ?customerId,
    'patient': ?patientId,
    if (doctorName.trim().isNotEmpty) 'doctor_name': doctorName.trim(),
    if (diagnosis.trim().isNotEmpty) 'diagnosis': diagnosis.trim(),
    if (consultationCategory.trim().isNotEmpty)
      'consultation_category': consultationCategory.trim().toUpperCase(),
    'medications': [for (final l in lines) l.toJson()],
  };
}

/// One drug being written onto a script.
class RxLineDraft {
  final String name;
  final int quantity;
  final int? itemId;
  final String dosage;
  final String duration;
  final String instructions;

  const RxLineDraft({
    required this.name,
    required this.quantity,
    this.itemId,
    this.dosage = '',
    this.duration = '',
    this.instructions = '',
  });

  Map<String, dynamic> toJson() => {
        'name': name.trim(),
        'quantity': quantity,
        'item': ?itemId,
        if (dosage.trim().isNotEmpty) 'dosage': dosage.trim(),
        if (duration.trim().isNotEmpty) 'duration': duration.trim(),
        if (instructions.trim().isNotEmpty) 'instructions': instructions.trim(),
      };
}

/// The fee a prescriber charges for a consultation band, read off the row the
/// API sent. Anything outside A–E costs nothing, which is also what the server
/// does with an unrecognised letter.
double consultationFee(Map<String, dynamic> prescriber, String? category) {
  final letter = (category ?? '').trim().toUpperCase();
  if (!const ['A', 'B', 'C', 'D', 'E'].contains(letter)) return 0;
  final fees = prescriber['consultation_fees'];
  final raw = fees is Map ? fees[letter] : prescriber['consult_fee_${letter.toLowerCase()}'];
  return num.tryParse('$raw')?.toDouble() ?? 0;
}

// ── Customer wallets ─────────────────────────────────────────────────────

/// POST body for a wallet top-up or deduction.
///
/// `method` is how the cash arrived and only means anything on a top-up — the
/// sales report attributes real money received by it — so a deduction, where
/// nothing crossed the counter, sends none.
Map<String, dynamic> walletBody(String amount,
    {String method = 'cash', String note = '', bool topUp = true}) {
  return {
    'amount': amount.trim(),
    if (topUp) 'method': method,
    if (note.trim().isNotEmpty) 'note': note.trim(),
  };
}

/// What a wallet charge of [amount] would leave behind: what the balance can
/// pay, and what becomes debt. Mirrors Customer.charge — shown before the
/// sale so nobody is surprised by a credit sale they didn't intend.
({double paid, double credit}) walletSplit(Object? balance, Object? amount) {
  final held = num.tryParse('${balance ?? ''}')?.toDouble() ?? 0;
  final due = num.tryParse('${amount ?? ''}')?.toDouble() ?? 0;
  final paid = held < due ? held : due;
  return (paid: paid < 0 ? 0 : paid, credit: due - paid < 0 ? 0 : due - paid);
}

// ── Stock checks and transfers ───────────────────────────────────────────

/// Actions on a stocktake. Applying one writes stock, so it is the admin's;
/// counting and abandoning are the shop floor's.
List<String> stockCheckActions(String? status, String? role) {
  if (!isPharmacyStaff(role)) return const [];
  switch (status) {
    case 'pending':
      return const ['count', 'cancel'];
    case 'in_progress':
      return isPharmacyAdmin(role)
          ? const ['count', 'complete', 'cancel']
          : const ['count', 'cancel'];
    default: // completed, cancelled
      return const [];
  }
}

/// Actions on a transfer between the retail and wholesale stores
/// (apps/inventory/models.py TransferRequest). Approving moves stock, so it
/// sits with the admin; receiving is the asking store confirming the shelf.
List<String> transferActions(String? status, String? role) {
  if (!isPharmacyStaff(role)) return const [];
  switch (status) {
    case 'pending':
      return isPharmacyAdmin(role) ? const ['approve', 'reject'] : const [];
    case 'approved':
      return const ['receive'];
    default: // rejected, received
      return const [];
  }
}

// ── Payment requests ─────────────────────────────────────────────────────

/// Actions on a dispenser's basket waiting at the till.
///
/// [mine] is true when the signed-in user raised it: only the dispenser
/// withdraws their own basket, and only a cashier takes one on.
List<String> paymentRequestActions(String? status, String? role,
    {required bool mine, required bool cashier}) {
  if (!isPharmacyStaff(role)) return const [];
  switch (status) {
    case 'pending':
      return [
        if (cashier) 'accept',
        if (cashier) 'reject',
        'complete',
        if (mine) 'cancel',
      ];
    case 'accepted':
      return ['complete', if (cashier) 'reject', if (mine) 'cancel'];
    default: // completed, rejected, cancelled
      return const [];
  }
}
