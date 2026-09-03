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
