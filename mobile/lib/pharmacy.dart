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

/// Grants the signed-in seat holds, set from /api/users/me/ (see Api.me).
/// The helpers below take a role and nothing else, so the grants live here
/// rather than being threaded through every call site.
Set<String> myGrants = const {};

/// The scheme an insurer seat answers for, set from /api/users/me/ the same
/// way. Null for everyone else, and for an insurer seat with no scheme yet.
int? myHmoId;

/// The admin role, or a pharmacist the admin trusted with the money screens.
/// The staff check still runs alongside this, so a grant admits no outsider.
bool isPharmacyAdmin(String? role) =>
    pharmacyAdminRoles.contains(role) || myGrants.contains('pharmacy_admin');
bool isPharmacyStaff(String? role) => pharmacyStaffRoles.contains(role);

/// Who gives the insurer's answer — to a request or a claim: the scheme's own
/// seat, or the pharmacy admin recording what the insurer said by phone.
/// Mirrors answers_for_insurer in apps/pharmacy/views.py.
bool answersForInsurer(String? role) =>
    role == 'hmo' ? myHmoId != null : isPharmacyAdmin(role);

/// Who keeps a scheme's price list (mirrors IsSchemePriceListEditor).
///
/// The insurer keeps its own — it agreed the contract, so a change to it is
/// entered by the party that agreed it — and the pharmacy admin keeps the list
/// of a scheme with no seat of its own. A seat with no scheme has no list to
/// keep. The counter reads and never writes: what a sale was covered at is not
/// a dispensing mistake's way out.
bool canEditPriceList(String? role, {Object? hmoId}) =>
    role == 'hmo' ? hmoId != null : isPharmacyAdmin(role);

/// The body ``POST /api/pharmacy/hmos/register/`` takes: a scheme, and the
/// seat that will run its desk, written together.
///
/// The scheme's own fields go nested under ``scheme`` because that half is the
/// ordinary insurer serializer — the platform admin signs the pair up, and the
/// seat minted carries ``is_admin``, so the scheme staffs itself from there.
///
/// Decimals travel as the strings the fields were typed in; DRF parses them,
/// and rounding a naira figure through a double on the way out would be this
/// client inventing a number nobody typed. A blank threshold is 0: "never ask
/// first", which is what the field left alone means.
Map<String, dynamic> schemeSignUpBody({
  required int? tenantId,
  required String name,
  required String adminPhone,
  required String adminPassword,
  String code = '',
  String contact = '',
  String email = '',
  String coveragePercent = '100',
  String preauthThreshold = '0',
  bool autoSubmitClaims = false,
  String adminName = '',
  String adminEmail = '',
}) {
  String blankTo(String value, String fallback) =>
      value.trim().isEmpty ? fallback : value.trim();
  return {
    'tenant': tenantId,
    'scheme': {
      'name': name.trim(),
      'code': code.trim(),
      'contact': contact.trim(),
      'email': email.trim(),
      'coverage_percent': blankTo(coveragePercent, '100'),
      'preauth_threshold': blankTo(preauthThreshold, '0'),
      'auto_submit_claims': autoSubmitClaims,
    },
    'admin_phone': adminPhone.trim(),
    'admin_name': adminName.trim(),
    'admin_email': adminEmail.trim(),
    'admin_password': adminPassword,
  };
}

/// What is still missing from a sign-up body, in words, or null when it is
/// ready to send. The API refuses all of this too — this only saves the round
/// trip, and says it in the same words the web form does.
///
/// ``withAdmin`` false is the platform admin adding a bare insurer row the
/// pharmacy will keep itself: there is no seat to check, so the scheme's own
/// fields are all that has to hold up.
String? schemeSignUpProblem(
  Map<String, dynamic> body, {
  bool withAdmin = true,
}) {
  final scheme = body['scheme'] as Map<String, dynamic>;
  if (body['tenant'] == null) {
    return 'Choose the organization whose claims this scheme answers for.';
  }
  if ('${scheme['name']}'.isEmpty) return 'Name the scheme.';
  if (!withAdmin) return null;
  if ('${body['admin_phone']}'.isEmpty) {
    return "Give the admin's phone number — it is how they sign in.";
  }
  if ('${body['admin_password']}'.length < 8) {
    return 'The admin password needs 8 characters or more.';
  }
  return null;
}

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
///
/// A sale that fills a prescription names it, and carries the number the
/// patient handed over: an order written at another facility is dispensed on
/// that number alone, and the API asks for it as the proof the patient is
/// standing there.
Map<String, dynamic> saleBody({
  required List<BasketLine> lines,
  required String paymentMethod,
  int? patientId,
  int? enrollmentId,
  int? prescriptionId,
  String? patientNumber,
  int? authorizationId,
}) {
  final insured = paymentMethod == 'hmo';
  final number = (patientNumber ?? '').trim();
  return {
    'payment_method': paymentMethod,
    'patient': ?patientId,
    if (insured && enrollmentId != null) 'enrollment': enrollmentId,
    // Only an insured sale can spend a clearance, so it travels with the card.
    if (insured && authorizationId != null) 'authorization': authorizationId,
    'prescription': ?prescriptionId,
    if (prescriptionId != null && number.isNotEmpty) 'patient_number': number,
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

/// POST body for /api/pharmacy/pre-authorizations/ — the basket, itemised.
///
/// The insurer answers drug by drug, so every medication travels as its own
/// line: a refusal on one does not cost the pharmacy the rest of the basket.
/// A line the patient pays nothing for is left out — the insurer is asked for
/// a positive figure, and the API refuses a zero one.
///
/// The ask is the gross. What the scheme actually owes (item rules, the annual
/// cap) is worked out server-side, and a clearance for more than is billed
/// still covers the sale.
Map<String, dynamic> preauthBody({
  required List<BasketLine> lines,
  required int enrollmentId,
}) {
  final billable = lines.where((l) => l.lineTotal > 0);
  return {
    'enrollment': enrollmentId,
    'amount': basketTotal(billable.toList()).toStringAsFixed(2),
    'items': [
      for (final l in billable)
        {
          'item': l.itemId,
          'quantity': l.quantity,
          'amount': l.lineTotal.toStringAsFixed(2),
        },
    ],
  };
}

/// Actions offered on an authorisation request (PreAuthorization._ALLOWED).
///
/// Staff raise and withdraw; only the admin records what the insurer said,
/// because that answer is what the pharmacy may later bill against. An
/// itemised request is answered medication by medication and settles itself
/// once every one is decided, so it is never answered as a whole.
List<String> preauthActions(String? status, String? role,
    {bool itemised = false}) {
  final answers = answersForInsurer(role);
  if (!isPharmacyStaff(role) && !answers) return const [];
  final decides = answers && !itemised && status == 'requested';
  return [
    if (decides) 'approve',
    if (decides) 'decline',
    // An answer typed wrong is withdrawn and recorded again. A spent or
    // withdrawn request stays as it is - the sale it cleared is already made.
    if (answers && !itemised && (status == 'approved' || status == 'declined'))
      'reopen',
    // Withdrawing the request is the pharmacy's, not the insurer's.
    if (isPharmacyStaff(role) && (status == 'requested' || status == 'approved'))
      'cancel',
  ];
}

/// Actions offered on a claim in its current state, mirroring the transitions
/// the API allows (apps/pharmacy/models.py Claim._ALLOWED). Staff send a claim;
/// the insurer's seat (or the admin for it) decides one; only the admin banks
/// the money.
List<String> claimActions(String? status, String? role) {
  final answers = answersForInsurer(role);
  if (!isPharmacyStaff(role) && !answers) return const [];
  final admin = isPharmacyAdmin(role);
  switch (status) {
    case 'draft':
    case 'rejected':
      return isPharmacyStaff(role) ? const ['submit'] : const [];
    case 'submitted':
      return answers ? const ['approve', 'reject'] : const [];
    case 'approved':
      return admin ? const ['pay'] : const [];
    default: // paid, cancelled — nothing left to do
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
