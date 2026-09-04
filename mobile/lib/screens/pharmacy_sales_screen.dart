import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_dispense_sheet.dart';
import 'report_scaffold.dart';

/// Sales — GET /api/pharmacy/sales/, and the counter that creates them.
///
/// A sale is a financial record: no edit, no delete. A mistake is reversed by
/// cancelling, which returns the stock to the batch it came from and voids any
/// claim raised against it.
class PharmacySalesScreen extends StatelessWidget {
  const PharmacySalesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/sales/',
      searchHint: 'Search by receipt number…',
      fabLabel: 'Dispense',
      emptyIcon: Icons.point_of_sale_outlined,
      emptyTitle: 'No sales yet',
      emptyMessage: 'Tap "Dispense" to serve the first patient.',
      savedMessage: 'Sale recorded.',
      filters: const [
        ReportFilter(param: 'status', anyLabel: 'Any status', options: {
          'pending': 'Unpaid',
          'paid': 'Paid',
          'cancelled': 'Cancelled',
        }),
        ReportFilter(param: 'payment_method', anyLabel: 'Any payment', options: {
          'cash': 'Cash',
          'card': 'Card',
          'transfer': 'Transfer',
          'hmo': 'HMO',
        }),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _SaleCard(row: row),
      onTap: (row) => _openSale(context, row),
      form: (_) => const DispenseSheet(),
    );
  }

  static Future<void> _openSale(
      BuildContext context, Map<String, dynamic> row) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => SaleSheet(sale: row),
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    // Cancelled sales are history, not takings — they stay out of every total.
    final live = items.where((r) => r['status'] != 'cancelled').toList();
    num sum(String key) => live.fold<num>(
        0, (total, r) => total + (num.tryParse('${r[key]}') ?? 0));
    final owed = sum('patient_payable') - sum('amount_paid');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.point_of_sale_outlined,
          title: 'Sales',
          subtitle: '${live.length} sale${live.length == 1 ? '' : 's'} listed',
          color: EnhancedTheme.primaryTeal,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.receipt_long_outlined,
              label: 'Billed',
              value: money(sum('total')),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.payments_outlined,
              label: 'Collected',
              value: money(sum('amount_paid')),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.hourglass_bottom,
              label: 'Owed',
              value: money(owed < 0 ? 0 : owed),
              color: EnhancedTheme.accentOrange),
        ]),
      ]),
    );
  }
}

Color _statusColor(String? status) => switch (status) {
      'paid' => EnhancedTheme.successGreen,
      'cancelled' => EnhancedTheme.errorRed,
      _ => EnhancedTheme.accentOrange,
    };

class _SaleCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _SaleCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final patient = '${row['patient_name'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['reference']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: _statusColor('${row['status']}')),
        ]),
        const SizedBox(height: 6),
        Text(
          [
            patient.isEmpty ? 'Walk-in' : patient,
            '${row['payment_method']}'.toUpperCase(),
          ].join(' · '),
          style: TextStyle(color: context.hintColor, fontSize: 13),
        ),
        const SizedBox(height: 4),
        Text('${money(row['total'])} · ${money(row['balance_due'])} due',
            style: const TextStyle(
                color: EnhancedTheme.primaryTeal, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

/// One sale: its lines, its money, and the two things left to do with it —
/// take the patient's payment, or reverse it.
class SaleSheet extends StatefulWidget {
  final Map<String, dynamic> sale;
  const SaleSheet({super.key, required this.sale});

  @override
  State<SaleSheet> createState() => _SaleSheetState();
}

class _SaleSheetState extends State<SaleSheet> {
  late Map<String, dynamic> _sale = widget.sale;
  bool _busy = false;

  Future<void> _refresh() async {
    final fresh = await api.get('/api/pharmacy/sales/${_sale['id']}/');
    if (mounted) setState(() => _sale = (fresh as Map).cast<String, dynamic>());
  }

  Future<void> _pay() async {
    final amount = await _askAmount(
        context, 'Take payment', 'Cash tendered (₦)', '${_sale['balance_due']}');
    if (amount == null) return;
    if (!mounted) return;
    // Only cash reaches the drawer, so how this payment arrived is asked
    // whenever the sale itself is not a cash sale - an insured bill is often
    // part settled in notes, part on a card.
    final method = _sale['payment_method'] == 'cash'
        ? 'cash'
        : await _askMethod(context);
    if (method == null) return;
    await _run('/api/pharmacy/sales/${_sale['id']}/pay/',
        {'amount': amount, 'method': method});
  }

  /// Settle the bill out of the customer's wallet.
  ///
  /// A wallet short of the bill still dispenses: the shortfall becomes debt
  /// and the sale is marked CREDIT, which keeps it out of revenue until it is
  /// paid. The confirmation says so, because that is a decision, not a detail.
  Future<void> _payWallet() async {
    // The sale carries the customer, not their balance — read it now so the
    // confirmation can name the shortfall rather than discovering it after.
    Object? balance;
    try {
      final c = await api.get('/api/customers/${_sale['customer']}/');
      balance = (c as Map)['wallet_balance'];
    } catch (_) {}
    if (!mounted) return;
    final split = walletSplit(balance, _sale['balance_due']);
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Pay from wallet'),
        content: Text(split.credit <= 0
            ? 'Take ${money(split.paid)} off the wallet?'
            : 'The wallet covers ${money(split.paid)}. '
                '${money(split.credit)} becomes the customer\'s debt and the '
                'sale is recorded as credit.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Pay')),
        ],
      ),
    );
    if (ok != true) return;
    await _run('/api/pos/sales/${_sale['id']}/pay-wallet/', {});
  }

  /// Take one line back: stock to its batch, refund out the chosen way.
  Future<void> _takeReturn(Map<String, dynamic> line) async {
    final qty = await _askAmount(context, 'Return ${line['item_name']}',
        'Units coming back', '${line['returnable'] ?? line['quantity']}');
    if (qty == null || !mounted) return;
    final method = await showDialog<String>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Refund how?'),
        children: [
          for (final m in const {
            'cash': 'Cash out of the drawer',
            'wallet': 'Back onto the wallet',
            'original': 'However it was paid',
          }.entries)
            SimpleDialogOption(
              onPressed: () => Navigator.of(context).pop(m.key),
              child: Text(m.value),
            ),
        ],
      ),
    );
    if (method == null || !mounted) return;
    final reason = await _askText(context, 'Return', 'Reason');
    if (!mounted) return;
    await _run('/api/pos/sales/${_sale['id']}/return/', {
      'line': line['id'],
      'quantity': int.tryParse(qty.trim()) ?? 0,
      'refund_method': method,
      'reason': reason ?? '',
    });
  }

  Future<void> _cancel() async {
    final reason = await _askText(context, 'Cancel sale', 'Reason');
    if (reason == null) return;
    await _run('/api/pharmacy/sales/${_sale['id']}/cancel/', {'reason': reason});
  }

  Future<void> _run(String path, Map<String, dynamic> body) async {
    setState(() => _busy = true);
    try {
      final r = await api.post(path, body);
      await _refresh();
      if (mounted) {
        showSuccess(context, '${(r as Map?)?['message'] ?? 'Done.'}');
      }
    } catch (e) {
      if (mounted) showError(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lines = (_sale['lines'] as List? ?? []).cast<Map<String, dynamic>>();
    final payments =
        (_sale['payments'] as List? ?? []).cast<Map<String, dynamic>>();
    final cancelled = _sale['status'] == 'cancelled';
    // A settled sale takes no more money — the API refuses it, so the button
    // goes rather than failing on the counter.
    final settled = (num.tryParse('${_sale['balance_due']}') ?? 0) <= 0;
    return Container(
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(
                child: Text('${_sale['reference']}',
                    style: TextStyle(
                        color: context.labelColor,
                        fontSize: 18,
                        fontWeight: FontWeight.w800)),
              ),
              ReportBadge(
                  text: '${_sale['status']}',
                  color: _statusColor('${_sale['status']}')),
            ]),
            Text(
              [
                '${_sale['patient_name'] ?? 'Walk-in'}',
                '${_sale['payment_method']}'.toUpperCase(),
              ].join(' · '),
              style: TextStyle(color: context.hintColor, fontSize: 13),
            ),
            const SizedBox(height: 12),
            for (final l in lines)
              ListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                title: Text('${l['item_name']}',
                    style: TextStyle(color: context.labelColor, fontSize: 14)),
                subtitle: Text('${units(l['quantity'])} × ${money(l['unit_price'])}'
                    '${l['batch_number'] == null ? '' : ' · batch ${l['batch_number']}'}'),
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  Text(money(l['line_total']),
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  // A line is returnable until every unit on it has come back;
                  // the server keeps that count, so the button follows it.
                  if (!cancelled && (num.tryParse('${l['returnable']}') ?? 0) > 0)
                    IconButton(
                      visualDensity: VisualDensity.compact,
                      tooltip: 'Take a return',
                      icon: const Icon(Icons.undo_outlined, size: 18),
                      onPressed: _busy ? null : () => _takeReturn(l),
                    ),
                ]),
              ),
            const Divider(),
            _MoneyRow('Total', money(_sale['total']), bold: true),
            if ((num.tryParse('${_sale['hmo_payable']}') ?? 0) > 0) ...[
              _MoneyRow('Covered by scheme', money(_sale['hmo_payable'])),
              _MoneyRow('Patient pays', money(_sale['patient_payable'])),
            ],
            _MoneyRow('Paid', money(_sale['amount_paid'])),
            if ((num.tryParse('${_sale['change_due']}') ?? 0) > 0) ...[
              _MoneyRow('Tendered', money(_sale['amount_tendered'])),
              _MoneyRow('Change given', money(_sale['change_due'])),
            ],
            _MoneyRow('Balance', money(_sale['balance_due'])),
            if (payments.isNotEmpty) ...[
              const Divider(),
              for (final p in payments)
                _MoneyRow(
                    '${p['method']}'.toUpperCase() +
                        ((num.tryParse('${p['change']}') ?? 0) > 0
                            ? ' · ${money(p['change'])} change'
                            : ''),
                    money(p['tendered'])),
            ],
            const SizedBox(height: 16),
            Wrap(spacing: 10, runSpacing: 10, children: [
              OutlinedButton.icon(
                onPressed: () => showModalBottomSheet<void>(
                  context: context,
                  isScrollControlled: true,
                  backgroundColor: Colors.transparent,
                  builder: (_) => ReceiptSheet(sale: _sale, lines: lines),
                ),
                icon: const Icon(Icons.receipt_long_outlined, size: 18),
                label: const Text('Receipt'),
              ),
              if (!cancelled && !settled)
                FilledButton.icon(
                  onPressed: _busy ? null : _pay,
                  style: FilledButton.styleFrom(
                      backgroundColor: EnhancedTheme.primaryTeal),
                  icon: const Icon(Icons.payments_outlined, size: 18),
                  label: const Text('Take payment'),
                ),
              // Only a sale with a customer on it has a wallet to draw on.
              if (!cancelled && !settled && _sale['customer'] != null)
                OutlinedButton.icon(
                  onPressed: _busy ? null : _payWallet,
                  icon: const Icon(Icons.account_balance_wallet_outlined,
                      size: 18),
                  label: const Text('Pay from wallet'),
                ),
              if (!cancelled)
                TextButton.icon(
                  onPressed: _busy ? null : _cancel,
                  style: TextButton.styleFrom(
                      foregroundColor: EnhancedTheme.errorRed),
                  icon: const Icon(Icons.undo, size: 18),
                  label: const Text('Cancel sale'),
                ),
            ]),
          ],
        ),
      ),
    );
  }
}

class _MoneyRow extends StatelessWidget {
  final String label;
  final String value;
  final bool bold;
  const _MoneyRow(this.label, this.value, {this.bold = false});

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      color: context.labelColor,
      fontWeight: bold ? FontWeight.w800 : FontWeight.w500,
      fontSize: bold ? 15 : 14,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [Text(label, style: style), Text(value, style: style)],
      ),
    );
  }
}

/// The receipt, rendered in-app from the sale the counter already has.
///
/// ponytail: no printing here. The server's /receipt/ endpoint is the printable
/// one, and a phone at the counter is showing this to the patient, not driving
/// a till roll. Wire up a print plugin only when someone asks for one.
class ReceiptSheet extends StatelessWidget {
  final Map<String, dynamic> sale;
  final List<Map<String, dynamic>> lines;
  const ReceiptSheet({super.key, required this.sale, required this.lines});

  @override
  Widget build(BuildContext context) {
    const mono = TextStyle(fontFamily: 'monospace', fontSize: 13, height: 1.5);
    String row(String left, String right) =>
        '${left.padRight(22).substring(0, 22)}${right.padLeft(12)}';
    final body = [
      row('Receipt', '${sale['reference']}'),
      row('Date', '${sale['created_at']}'.replaceAll('T', ' ').split('.').first),
      if ((sale['patient_name'] ?? '').toString().isNotEmpty)
        row('Patient', '${sale['patient_name']}'),
      '',
      for (final l in lines) ...[
        '${l['item_name']}',
        row('  ${units(l['quantity'])} × ${money(l['unit_price'])}',
            money(l['line_total'])),
      ],
      '',
      row('Total', money(sale['total'])),
      if ((num.tryParse('${sale['hmo_payable']}') ?? 0) > 0) ...[
        row('Covered by scheme', money(sale['hmo_payable'])),
        row('Patient pays', money(sale['patient_payable'])),
      ],
      row('Paid', money(sale['amount_paid'])),
      if ((num.tryParse('${sale['change_due']}') ?? 0) > 0) ...[
        row('Tendered', money(sale['amount_tendered'])),
        row('Change given', money(sale['change_due'])),
      ],
      row('Balance', money(sale['balance_due'])),
    ].join('\n');
    return Container(
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
      child: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (sale['status'] == 'cancelled')
            const ReportBadge(text: 'cancelled', color: EnhancedTheme.errorRed),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Text(body, style: mono),
          ),
        ]),
      ),
    );
  }
}

/// Small prompts shared by the sale and claim actions. A cancelled prompt
/// returns null, which every caller treats as "do nothing".
Future<String?> _askAmount(BuildContext context, String title, String label,
    String initial) async {
  final controller = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(labelText: label),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            final value = controller.text.trim();
            Navigator.of(dialogContext).pop(value.isEmpty ? null : value);
          },
          child: const Text('OK'),
        ),
      ],
    ),
  );
}

/// How the money arrived. Cash is the counter default; the other two are
/// settled elsewhere and never touch the drawer.
Future<String?> _askMethod(BuildContext context) => showDialog<String>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: const Text('How was it paid?'),
        children: [
          for (final entry in const {
            'cash': 'Cash',
            'card': 'Card',
            'transfer': 'Transfer',
          }.entries)
            SimpleDialogOption(
              onPressed: () => Navigator.of(dialogContext).pop(entry.key),
              child: Text(entry.value),
            ),
        ],
      ),
    );

Future<String?> _askText(
    BuildContext context, String title, String label) async {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: InputDecoration(labelText: label),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Back')),
        FilledButton(
            onPressed: () =>
                Navigator.of(dialogContext).pop(controller.text.trim()),
            child: const Text('Confirm')),
      ],
    ),
  );
}

/// Re-exported so the claims screen can use the same prompts.
Future<String?> askAmount(BuildContext context, String title, String label,
        [String initial = '']) =>
    _askAmount(context, title, label, initial);

Future<String?> askText(BuildContext context, String title, String label) =>
    _askText(context, title, label);
