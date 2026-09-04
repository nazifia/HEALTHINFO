import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'pharmacy_kit.dart';
import 'pharmacy_sales_screen.dart' show askAmount, askText;
import 'report_scaffold.dart';

/// Stock transfers — GET /api/inventory/transfers/.
///
/// The same drug is a separate row in the retail and wholesale stores, so
/// moving units between them is a request, not an edit: the sending store says
/// how many it can actually spare, and the stock crosses in that same call.
///
/// Approving moves stock, so it is the admin's. Receiving is the asking store
/// confirming the units reached its shelf.
class TransfersScreen extends StatelessWidget {
  const TransfersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final role = snap.data;
        return ReportListScreen(
          path: '/api/inventory/transfers/',
          fabLabel: 'Ask for stock',
          showFab: isPharmacyStaff(role),
          emptyIcon: Icons.swap_horiz_outlined,
          emptyTitle: 'No transfers yet',
          emptyMessage: 'Ask the other store for units it can spare.',
          savedMessage: 'Transfer requested.',
          filters: const [
            ReportFilter(param: 'status', anyLabel: 'Any state', options: {
              'pending': 'Waiting',
              'approved': 'Approved',
              'received': 'Received',
              'rejected': 'Refused',
            }),
          ],
          card: (row, reload, edit) =>
              _TransferCard(row: row, role: role, reload: reload),
          form: (_) => const _TransferForm(),
        );
      },
    );
  }
}

class _TransferCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final String? role;
  final VoidCallback reload;
  const _TransferCard(
      {required this.row, required this.role, required this.reload});

  Future<void> _act(BuildContext context, String action) async {
    Map<String, dynamic>? body;
    if (action == 'approve') {
      // The sending store may only be able to spare part of it; the field is
      // seeded with what was asked for.
      final qty = await askAmount(context, 'Approve transfer',
          'Units to send', '${row['requested_quantity']}');
      if (qty == null) return;
      body = {'quantity': int.tryParse(qty.trim()) ?? row['requested_quantity']};
    } else if (action == 'reject') {
      if (!context.mounted) return;
      final reason = await askText(context, 'Refuse transfer', 'Reason');
      body = {'reason': reason ?? ''};
    }
    if (!context.mounted) return;
    await runAction(context, '/api/inventory/transfers/${row['id']}/$action/',
        body: body, after: () async => reload());
  }

  @override
  Widget build(BuildContext context) {
    final sent = row['approved_quantity'];
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['from_item_name']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: statusColor(row['status'])),
        ]),
        const SizedBox(height: 4),
        Text('${row['direction'] ?? ''} → ${row['to_item_name']}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        const SizedBox(height: 4),
        Text(
            'Asked ${row['requested_quantity']}'
            '${(num.tryParse('$sent') ?? 0) > 0 ? ' · sent $sent' : ''}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if ('${row['notes'] ?? ''}'.trim().isNotEmpty)
          Text('${row['notes']}',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
        ActionRow(
          actions: transferActions('${row['status']}', role),
          onAction: (a) => _act(context, a),
        ),
      ]),
    );
  }
}

class _TransferForm extends StatefulWidget {
  const _TransferForm();

  @override
  State<_TransferForm> createState() => _TransferFormState();
}

class _TransferFormState extends State<_TransferForm> {
  final _qty = TextEditingController(text: '1');
  final _notes = TextEditingController();
  Map<String, dynamic>? _from;
  Map<String, dynamic>? _to;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _qty.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pick({required bool source}) async {
    final row = await pickRow(
      context,
      path: '/api/inventory/items/',
      title: source ? 'Take units from' : 'Put units into',
      hint: 'Drug name or brand…',
      label: (r) => '${r['name']} (${r['store']})',
      subtitle: (r) => '${r['quantity_on_hand'] ?? 0} on hand',
    );
    if (row == null) return;
    setState(() => source ? _from = row : _to = row);
  }

  Future<void> _submit() async {
    final qty = int.tryParse(_qty.text.trim()) ?? 0;
    if (_from == null || _to == null || qty < 1) {
      setState(() => _error = 'Pick both item lines and a quantity.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post('/api/inventory/transfers/', {
        'from_item': _from!['id'],
        'to_item': _to!['id'],
        'requested_quantity': qty,
        'notes': _notes.text.trim(),
      });
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _slot(String label, Map<String, dynamic>? row, bool source) {
    return InputDecorator(
      decoration: InputDecoration(labelText: label),
      child: Row(children: [
        Expanded(
          child: Text(
            row == null ? 'Not picked' : '${row['name']} (${row['store']})',
            style: TextStyle(
                color: row == null ? context.hintColor : context.labelColor),
            overflow: TextOverflow.ellipsis,
          ),
        ),
        TextButton(
            onPressed: () => _pick(source: source),
            child: Text(row == null ? 'Pick' : 'Change')),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: 'Ask for stock',
      saving: _saving,
      error: _error,
      submitLabel: 'Send request',
      onSubmit: _submit,
      children: [
        // The API refuses a transfer where both lines sit in the same store —
        // there would be nothing to move.
        _slot('From (the store that has it)', _from, true),
        const SizedBox(height: 12),
        _slot('To (the store that needs it)', _to, false),
        const SizedBox(height: 12),
        TextField(
          controller: _qty,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Units wanted'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Why (optional)'),
        ),
      ],
    );
  }
}
