import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'pharmacy_sales_screen.dart' show askText;
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Payment requests — GET /api/pos/payment-requests/.
///
/// The dispenser's basket, waiting on a cashier. Nothing leaves the shelf
/// until it is completed: until then this is a list of what someone intends to
/// sell, not a sale. Completing it is where stock actually moves, and it is
/// all or nothing — a line that cannot be filled leaves the basket open
/// rather than half-dispensing it.
class PaymentRequestsScreen extends StatelessWidget {
  const PaymentRequestsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_Who>(
      future: _who(),
      builder: (context, snap) {
        final who = snap.data ?? const _Who(role: null, userId: null, cashier: false);
        return ReportListScreen(
          path: '/api/pos/payment-requests/',
          searchHint: 'Reference or buyer…',
          fabLabel: 'New request',
          showFab: isPharmacyStaff(who.role),
          emptyIcon: Icons.pending_actions_outlined,
          emptyTitle: 'Nothing waiting at the till',
          emptyMessage: 'Build a basket here and a cashier takes the money.',
          savedMessage: 'Request sent to the till.',
          filters: const [
            ReportFilter(param: 'status', anyLabel: 'Any state', options: {
              'pending': 'Waiting',
              'accepted': 'With a cashier',
              'completed': 'Sold',
              'rejected': 'Refused',
              'cancelled': 'Withdrawn',
            }),
            ReportFilter(param: 'store', anyLabel: 'Both stores', options: {
              'retail': 'Retail',
              'wholesale': 'Wholesale',
            }),
          ],
          card: (row, reload, edit) =>
              _RequestCard(row: row, who: who, reload: reload),
          form: (_) => const _RequestForm(),
        );
      },
    );
  }

  /// Role, user id, and whether this user is set up to take money — the three
  /// facts that decide which buttons a basket offers.
  static Future<_Who> _who() async {
    final role = await api.myRole();
    final id = await api.myId();
    var cashier = false;
    if (id != null) {
      try {
        final rows = await api
            .getList('/api/pos/cashiers/', {'user': '$id', 'is_active': 'true'});
        cashier = rows.isNotEmpty;
      } catch (_) {}
    }
    return _Who(role: role, userId: id, cashier: cashier);
  }
}

class _Who {
  final String? role;
  final int? userId;
  final bool cashier;
  const _Who({required this.role, required this.userId, required this.cashier});
}

class _RequestCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final _Who who;
  final VoidCallback reload;
  const _RequestCard(
      {required this.row, required this.who, required this.reload});

  Future<void> _act(BuildContext context, String action) async {
    Object? body;
    if (action == 'reject') {
      final reason = await askText(context, 'Refuse request', 'Reason');
      if (!context.mounted) return;
      body = {'reason': reason ?? ''};
    } else if (action == 'complete') {
      final method = await _askMethod(context);
      if (method == null || !context.mounted) return;
      body = {'payment_method': method};
    }
    if (!context.mounted) return;
    await runAction(
        context, '/api/pos/payment-requests/${row['id']}/$action/',
        body: body, after: () async => reload());
  }

  @override
  Widget build(BuildContext context) {
    final lines = ((row['lines'] ?? []) as List).cast<Map<String, dynamic>>();
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
          Text(money(row['total_amount']),
              style: TextStyle(
                  color: context.labelColor,
                  fontWeight: FontWeight.w800,
                  fontSize: 15)),
          const SizedBox(width: 8),
          ReportBadge(
              text: '${row['status']}', color: statusColor(row['status'])),
        ]),
        const SizedBox(height: 4),
        Text(
            '${row['buyer_name']?.toString().isNotEmpty == true ? row['buyer_name'] : row['customer_name'] ?? 'Walk-in'}'
            ' · ${lines.length} line(s) · ${row['store']}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        Text(
            'Raised by ${row['dispenser_name'] ?? '—'}'
            '${row['cashier_name'] == null ? '' : ' · till ${row['cashier_name']}'}',
            style: TextStyle(color: context.hintColor, fontSize: 12)),
        for (final l in lines.take(3))
          Text('  ${l['name']} ×${l['quantity']} · ${money(l['subtotal'])}',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
        if (lines.length > 3)
          Text('  +${lines.length - 3} more',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
        ActionRow(
          actions: paymentRequestActions('${row['status']}', who.role,
              mine: row['dispenser'] == who.userId, cashier: who.cashier),
          onAction: (a) => _act(context, a),
        ),
      ]),
    );
  }
}

Future<String?> _askMethod(BuildContext context) {
  return showDialog<String>(
    context: context,
    builder: (context) => SimpleDialog(
      title: const Text('How was it paid?'),
      children: [
        for (final m in const {
          'cash': 'Cash',
          'card': 'Card / POS',
          'transfer': 'Transfer',
          'wallet': 'Customer wallet',
        }.entries)
          SimpleDialogOption(
            onPressed: () => Navigator.of(context).pop(m.key),
            child: Text(m.value),
          ),
      ],
    ),
  );
}

class _RequestForm extends StatefulWidget {
  const _RequestForm();

  @override
  State<_RequestForm> createState() => _RequestFormState();
}

class _RequestFormState extends State<_RequestForm> {
  final _buyer = TextEditingController();
  final _lines = <BasketLine>[];
  Map<String, dynamic>? _customer;
  String _store = 'retail';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _buyer.dispose();
    super.dispose();
  }

  Future<void> _addLine() async {
    final item = await pickRow(
      context,
      path: '/api/inventory/items/',
      title: 'Add to the basket',
      hint: 'Drug name or brand…',
      query: {'store': _store},
      label: (r) => '${r['name']}',
      subtitle: (r) => '${money(r['unit_price'])} · '
          '${r['quantity_on_hand'] ?? 0} on hand',
    );
    if (item == null || !mounted) return;
    final qty = await showDialog<int>(
      context: context,
      builder: (context) {
        final c = TextEditingController(text: '1');
        return AlertDialog(
          title: Text('${item['name']}'),
          content: TextField(
            controller: c,
            autofocus: true,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Quantity'),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cancel')),
            FilledButton(
                onPressed: () =>
                    Navigator.of(context).pop(int.tryParse(c.text.trim())),
                child: const Text('Add')),
          ],
        );
      },
    );
    if (qty == null || qty < 1) return;
    setState(() => _lines.add(BasketLine(
          itemId: item['id'] as int,
          name: '${item['name']}',
          unitPrice: num.tryParse('${item['unit_price']}')?.toDouble() ?? 0,
          quantity: qty,
        )));
  }

  Future<void> _pickCustomer() async {
    final row = await pickRow(
      context,
      path: '/api/customers/',
      title: 'Who is buying?',
      hint: 'Name or phone…',
      label: (r) => '${r['name']}',
      subtitle: (r) => '${r['phone'] ?? ''}',
    );
    if (row != null) {
      setState(() {
        _customer = row;
        _buyer.text = '${row['name']}';
      });
    }
  }

  Future<void> _submit() async {
    if (_lines.isEmpty) {
      setState(() => _error = 'Put something in the basket first.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post('/api/pos/payment-requests/', {
        'store': _store,
        'buyer_name': _buyer.text.trim(),
        'customer': _customer?['id'],
        // The server prices and totals the basket; these are what the
        // dispenser saw on the shelf label.
        'items': [
          for (final l in _lines)
            {
              'item': l.itemId,
              'name': l.name,
              'quantity': l.quantity,
              'unit_price': l.unitPrice.toStringAsFixed(2),
            }
        ],
      });
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: 'New payment request',
      saving: _saving,
      error: _error,
      submitLabel: 'Send to the till',
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _store,
          decoration: const InputDecoration(labelText: 'Counter'),
          items: const [
            DropdownMenuItem(value: 'retail', child: Text('Retail')),
            DropdownMenuItem(value: 'wholesale', child: Text('Wholesale')),
          ],
          onChanged: (v) => setState(() {
            _store = v ?? 'retail';
            _lines.clear();
          }),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _buyer,
              decoration: const InputDecoration(
                  labelText: 'Buyer', hintText: 'Walk-in'),
            ),
          ),
          TextButton(onPressed: _pickCustomer, child: const Text('Find')),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: Text('Basket — ${money(basketTotal(_lines))}',
                style: TextStyle(
                    color: context.labelColor, fontWeight: FontWeight.w700)),
          ),
          TextButton.icon(
            onPressed: _addLine,
            icon: const Icon(Icons.add, size: 18),
            label: const Text('Add item'),
          ),
        ]),
        Text('An estimate for the patient — the till prices the sale.',
            style: TextStyle(color: context.hintColor, fontSize: 12)),
        for (var i = 0; i < _lines.length; i++)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: Text('${_lines[i].name} ×${_lines[i].quantity}',
                style: TextStyle(color: context.labelColor, fontSize: 14)),
            subtitle: Text(money(_lines[i].lineTotal),
                style: TextStyle(color: context.hintColor, fontSize: 12)),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline, size: 18),
              onPressed: () => setState(() => _lines.removeAt(i)),
            ),
          ),
      ],
    );
  }
}
