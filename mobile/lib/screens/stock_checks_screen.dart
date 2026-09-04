import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Stocktakes — GET /api/inventory/stock-checks/.
///
/// Raise a count, enter what was found, then apply the gaps. The expected
/// quantity is snapshotted when a line is raised, so a sale mid-count doesn't
/// silently move the target somebody is counting against.
///
/// Applying a count writes stock, so it sits with the admin. Counting and
/// abandoning are the shop floor's.
class StockChecksScreen extends StatelessWidget {
  const StockChecksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final role = snap.data;
        return ReportListScreen(
          path: '/api/inventory/stock-checks/',
          fabLabel: 'New count',
          showFab: isPharmacyStaff(role),
          emptyIcon: Icons.fact_check_outlined,
          emptyTitle: 'No stocktakes yet',
          emptyMessage: 'Raise a count, then walk the shelf against it.',
          savedMessage: 'Stock check raised.',
          filters: const [
            ReportFilter(param: 'status', anyLabel: 'Any state', options: {
              'pending': 'Not started',
              'in_progress': 'Counting',
              'completed': 'Applied',
              'cancelled': 'Abandoned',
            }),
            ReportFilter(param: 'store', anyLabel: 'Both stores', options: {
              'retail': 'Retail',
              'wholesale': 'Wholesale',
            }),
          ],
          card: (row, reload, edit) => _CheckCard(row: row),
          onTap: (row) => _open(context, row, role),
          form: (_) => const _NewCheckForm(),
        );
      },
    );
  }

  static Future<void> _open(
      BuildContext context, Map<String, dynamic> row, String? role) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => StockCheckSheet(check: row, role: role),
    );
  }
}

class _CheckCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _CheckCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final totals = (row['totals'] as Map?) ?? const {};
    final gap = num.tryParse('${totals['discrepancy_units']}') ?? 0;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['store']} count #${row['id']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: statusColor(row['status'])),
        ]),
        const SizedBox(height: 4),
        Text(
            '${totals['counted'] ?? 0} of ${totals['lines'] ?? 0} lines counted'
            ' · raised by ${row['created_by_name'] ?? '—'}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if (gap != 0)
          Text(
              '${gap > 0 ? '+' : ''}$gap units · '
              '${money(totals['discrepancy_value'])} at cost',
              style: TextStyle(
                  color: gap < 0
                      ? EnhancedTheme.errorRed
                      : EnhancedTheme.accentOrange,
                  fontSize: 13,
                  fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

/// One stocktake: every line, the count entered against it, and the gap.
class StockCheckSheet extends StatefulWidget {
  final Map<String, dynamic> check;
  final String? role;
  const StockCheckSheet({super.key, required this.check, this.role});

  @override
  State<StockCheckSheet> createState() => _StockCheckSheetState();
}

class _StockCheckSheetState extends State<StockCheckSheet> {
  late Map<String, dynamic> _check = widget.check;
  // Counts typed but not yet sent, keyed by item id.
  final Map<int, TextEditingController> _counts = {};
  bool _busy = false;

  @override
  void dispose() {
    for (final c in _counts.values) {
      c.dispose();
    }
    super.dispose();
  }

  List<Map<String, dynamic>> get _lines =>
      ((_check['lines'] ?? []) as List).cast<Map<String, dynamic>>();

  TextEditingController _controller(Map<String, dynamic> line) {
    final id = line['item'] as int;
    return _counts.putIfAbsent(
        id,
        () => TextEditingController(
            text: line['actual_quantity'] == null
                ? ''
                : '${line['actual_quantity']}'));
  }

  Future<void> _refresh() async {
    final fresh =
        await api.get('/api/inventory/stock-checks/${_check['id']}/');
    if (mounted) setState(() => _check = (fresh as Map).cast<String, dynamic>());
  }

  Future<void> _act(String action) async {
    if (action == 'count') return _sendCounts();
    setState(() => _busy = true);
    await runAction(
        context, '/api/inventory/stock-checks/${_check['id']}/$action/',
        after: _refresh);
    if (mounted) setState(() => _busy = false);
  }

  /// Send every line that has a number typed against it. Blank stays blank:
  /// an uncounted line is not a line counted as zero.
  Future<void> _sendCounts() async {
    final rows = [
      for (final line in _lines)
        if (int.tryParse(_controller(line).text.trim()) != null)
          {
            'item': line['item'],
            'quantity': int.parse(_controller(line).text.trim()),
          }
    ];
    if (rows.isEmpty) return;
    setState(() => _busy = true);
    // The count endpoint takes a bare list of lines, not an object.
    await runAction(
        context, '/api/inventory/stock-checks/${_check['id']}/count/',
        body: rows, after: _refresh);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final totals = (_check['totals'] as Map?) ?? const {};
    final actions = stockCheckActions('${_check['status']}', widget.role);
    final open = actions.contains('count');
    return Container(
      constraints:
          BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.9),
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text('${_check['store']} count #${_check['id']}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
            ),
            ReportBadge(
                text: '${_check['status']}',
                color: statusColor(_check['status'])),
          ]),
          const SizedBox(height: 12),
          KpiRow(tiles: [
            KpiTile(
                icon: Icons.checklist_outlined,
                label: 'Counted',
                value: '${totals['counted'] ?? 0}/${totals['lines'] ?? 0}',
                color: EnhancedTheme.primaryTeal),
            KpiTile(
                icon: Icons.difference_outlined,
                label: 'Unit gap',
                value: units(totals['discrepancy_units']),
                color: EnhancedTheme.accentOrange),
            KpiTile(
                icon: Icons.savings_outlined,
                label: 'At cost',
                value: money(totals['discrepancy_value']),
                color: EnhancedTheme.accentCyan),
          ]),
          const Divider(),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: _lines.length,
              itemBuilder: (context, i) {
                final l = _lines[i];
                final gap = l['discrepancy'];
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${l['item_name']}',
                              style: TextStyle(
                                  color: context.labelColor, fontSize: 14)),
                          Text(
                              'Books say ${l['expected_quantity']}'
                              '${l['actual_quantity'] == null ? '' : ' · gap $gap'}',
                              style: TextStyle(
                                  color: context.hintColor, fontSize: 12)),
                        ],
                      ),
                    ),
                    SizedBox(
                      width: 90,
                      child: TextField(
                        controller: _controller(l),
                        enabled: open,
                        keyboardType: TextInputType.number,
                        textAlign: TextAlign.end,
                        decoration: const InputDecoration(
                            labelText: 'Found', isDense: true),
                      ),
                    ),
                  ]),
                );
              },
            ),
          ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: LinearProgressIndicator(minHeight: 2),
            )
          else
            ActionRow(actions: actions, onAction: _act),
        ],
      ),
    );
  }
}

class _NewCheckForm extends StatefulWidget {
  const _NewCheckForm();

  @override
  State<_NewCheckForm> createState() => _NewCheckFormState();
}

class _NewCheckFormState extends State<_NewCheckForm> {
  final _notes = TextEditingController();
  final _items = <Map<String, dynamic>>[];
  String _store = 'retail';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  Future<void> _addItem() async {
    final row = await pickRow(
      context,
      path: '/api/inventory/items/',
      title: 'Add an item to count',
      hint: 'Drug name or brand…',
      query: {'store': _store},
      label: (r) => '${r['name']}',
      subtitle: (r) => '${r['quantity_on_hand'] ?? 0} on the books',
    );
    if (row == null) return;
    if (_items.any((i) => i['id'] == row['id'])) return;
    setState(() => _items.add(row));
  }

  Future<void> _submit() async {
    if (_items.isEmpty) {
      setState(() => _error = 'Pick at least one item to count.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post('/api/inventory/stock-checks/', {
        'store': _store,
        'notes': _notes.text.trim(),
        'items': [for (final i in _items) i['id']],
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
      title: 'New stock check',
      saving: _saving,
      error: _error,
      submitLabel: 'Raise count',
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _store,
          decoration: const InputDecoration(labelText: 'Store'),
          items: const [
            DropdownMenuItem(value: 'retail', child: Text('Retail')),
            DropdownMenuItem(value: 'wholesale', child: Text('Wholesale')),
          ],
          onChanged: (v) => setState(() {
            _store = v ?? 'retail';
            // Items belong to one store, so switching stores drops what was
            // picked rather than raising a count against the wrong shelf.
            _items.clear();
          }),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: Text('Items (${_items.length})',
                style: TextStyle(
                    color: context.labelColor, fontWeight: FontWeight.w700)),
          ),
          TextButton.icon(
            onPressed: _addItem,
            icon: const Icon(Icons.add, size: 18),
            label: const Text('Add item'),
          ),
        ]),
        for (var i = 0; i < _items.length; i++)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: Text('${_items[i]['name']}',
                style: TextStyle(color: context.labelColor, fontSize: 14)),
            subtitle: Text('${_items[i]['quantity_on_hand'] ?? 0} on the books',
                style: TextStyle(color: context.hintColor, fontSize: 12)),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline, size: 18),
              onPressed: () => setState(() => _items.removeAt(i)),
            ),
          ),
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Notes (optional)'),
        ),
      ],
    );
  }
}
