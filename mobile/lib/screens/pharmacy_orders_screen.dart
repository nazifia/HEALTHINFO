import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_stock_screen.dart' show loadStockItems;
import 'report_scaffold.dart';

/// Purchase orders — GET /api/pharmacy/purchase-orders/.
///
/// An order records what was asked for; each line counts what has actually
/// landed, and the status follows from that rather than being set by hand.
/// Suppliers part-ship and invoice at another price, so receiving is per line
/// and takes the invoice cost with it.
class PharmacyOrdersScreen extends StatelessWidget {
  const PharmacyOrdersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) => ReportListScreen(
        path: '/api/pharmacy/purchase-orders/',
        searchHint: 'Search by order number…',
        fabLabel: 'New order',
        showFab: isPharmacyStaff(snap.data),
        emptyIcon: Icons.local_shipping_outlined,
        emptyTitle: 'No purchase orders yet',
        emptyMessage: 'Tap "New order" to ask a supplier for stock.',
        savedMessage: 'Order created.',
        filters: const [
          ReportFilter(param: 'status', anyLabel: 'Any status', options: {
            'draft': 'Draft',
            'submitted': 'Submitted',
            'partial': 'Part-delivered',
            'received': 'Received',
            'cancelled': 'Cancelled',
          }),
        ],
        header: (items) => _Header(items: items),
        card: (row, reload, edit) => _OrderCard(row: row),
        onTap: (row) => _openOrder(context, row),
        form: (_) => const _OrderForm(),
      ),
    );
  }

  static Future<void> _openOrder(
      BuildContext context, Map<String, dynamic> row) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _OrderSheet(order: row),
    );
  }
}

Color _orderColor(String? status) => switch (status) {
      'received' => EnhancedTheme.successGreen,
      'cancelled' => EnhancedTheme.errorRed,
      'partial' => EnhancedTheme.accentOrange,
      'submitted' => EnhancedTheme.accentCyan,
      _ => EnhancedTheme.infoBlue,
    };

/// Units still owed by the supplier across an order's lines.
int _outstanding(Map<String, dynamic> order) =>
    ((order['lines'] as List?) ?? []).fold<int>(
        0, (sum, l) => sum + ((l['outstanding'] as int?) ?? 0));

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final open = items
        .where((r) => r['status'] == 'submitted' || r['status'] == 'partial')
        .toList();
    final onOrder =
        open.fold<int>(0, (sum, r) => sum + _outstanding(r));
    final value = items
        .where((r) => r['status'] != 'cancelled')
        .fold<num>(0, (sum, r) => sum + (num.tryParse('${r['total_cost']}') ?? 0));
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.local_shipping_outlined,
          title: 'Purchase orders',
          subtitle: '${items.length} order${items.length == 1 ? '' : 's'}',
          color: EnhancedTheme.infoBlue,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.pending_actions_outlined,
              label: 'Awaiting delivery',
              value: units(open.length),
              color: EnhancedTheme.accentOrange),
          KpiTile(
              icon: Icons.inventory_outlined,
              label: 'Units on order',
              value: units(onOrder),
              color: EnhancedTheme.primaryTeal),
        ]),
        const SizedBox(height: 8),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.request_quote_outlined,
              label: 'Ordered value',
              value: money(value),
              color: EnhancedTheme.accentPurple),
          KpiTile(
              icon: Icons.done_all,
              label: 'Received',
              value: units(items.where((r) => r['status'] == 'received').length),
              color: EnhancedTheme.successGreen),
        ]),
      ]),
    );
  }
}

class _OrderCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _OrderCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final lines = ((row['lines'] as List?) ?? []).length;
    final outstanding = _outstanding(row);
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['supplier_name'] ?? 'Order'} · ${row['reference']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: _orderColor('${row['status']}')),
        ]),
        const SizedBox(height: 6),
        Text(
          [
            '$lines line${lines == 1 ? '' : 's'}',
            if (outstanding > 0) '${units(outstanding)} outstanding',
            if (row['expected_date'] != null) 'due ${row['expected_date']}',
          ].join(' · '),
          style: TextStyle(color: context.hintColor, fontSize: 13),
        ),
        const SizedBox(height: 4),
        Text(money(row['total_cost']),
            style: const TextStyle(
                color: EnhancedTheme.primaryTeal, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

/// One order: its lines, what is still owed on each, and the delivery form.
class _OrderSheet extends StatefulWidget {
  final Map<String, dynamic> order;
  const _OrderSheet({required this.order});

  @override
  State<_OrderSheet> createState() => _OrderSheetState();
}

class _OrderSheetState extends State<_OrderSheet> {
  late Map<String, dynamic> _order = widget.order;
  String? _role;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    api.myRole().then((r) {
      if (mounted) setState(() => _role = r);
    });
  }

  Future<void> _refresh() async {
    final fresh = await api.get('/api/pharmacy/purchase-orders/${_order['id']}/');
    if (mounted) setState(() => _order = (fresh as Map).cast<String, dynamic>());
  }

  Future<void> _act(String action) async {
    setState(() => _busy = true);
    try {
      final r = await api
          .post('/api/pharmacy/purchase-orders/${_order['id']}/$action/');
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

  Future<void> _receive() async {
    final booked = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ReceiveForm(order: _order),
    );
    if (booked != true) return;
    await _refresh();
    if (mounted) showSuccess(context, 'Delivery booked in.');
  }

  @override
  Widget build(BuildContext context) {
    final lines = ((_order['lines'] as List?) ?? []).cast<Map<String, dynamic>>();
    final actions = orderActions('${_order['status']}', _role);
    final canReceive = _outstanding(_order) > 0 &&
        _order['status'] != 'cancelled' &&
        _order['status'] != 'draft';
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
                child: Text('${_order['reference']}',
                    style: TextStyle(
                        color: context.labelColor,
                        fontSize: 18,
                        fontWeight: FontWeight.w800)),
              ),
              ReportBadge(
                  text: '${_order['status']}',
                  color: _orderColor('${_order['status']}')),
            ]),
            Text(
              [
                '${_order['supplier_name'] ?? ''}',
                if (_order['expected_date'] != null)
                  'due ${_order['expected_date']}',
              ].where((v) => v.isNotEmpty).join(' · '),
              style: TextStyle(color: context.hintColor, fontSize: 13),
            ),
            const SizedBox(height: 12),
            for (final l in lines)
              ListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                title: Text('${l['item_name']}',
                    style: TextStyle(color: context.labelColor, fontSize: 14)),
                subtitle: Text(
                    '${units(l['quantity_received'])} of ${units(l['quantity_ordered'])} received'
                    ' · ${money(l['unit_cost'])} each'),
                trailing: (l['outstanding'] as int? ?? 0) > 0
                    ? ReportBadge(
                        text: '${l['outstanding']} due',
                        color: EnhancedTheme.accentOrange)
                    : const ReportBadge(
                        text: 'complete', color: EnhancedTheme.successGreen),
              ),
            const Divider(),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Order value',
                    style: TextStyle(
                        color: context.labelColor, fontWeight: FontWeight.w800)),
                Text(money(_order['total_cost']),
                    style: TextStyle(
                        color: context.labelColor, fontWeight: FontWeight.w800)),
              ],
            ),
            const SizedBox(height: 16),
            Wrap(spacing: 10, runSpacing: 10, children: [
              if (canReceive)
                FilledButton.icon(
                  onPressed: _busy ? null : _receive,
                  style: FilledButton.styleFrom(
                      backgroundColor: EnhancedTheme.primaryTeal),
                  icon: const Icon(Icons.local_shipping_outlined, size: 18),
                  label: const Text('Receive delivery'),
                ),
              for (final a in actions)
                if (a == 'cancel')
                  TextButton.icon(
                    onPressed: _busy ? null : () => _act(a),
                    style: TextButton.styleFrom(
                        foregroundColor: EnhancedTheme.errorRed),
                    icon: const Icon(Icons.close, size: 18),
                    label: const Text('Cancel order'),
                  )
                else
                  OutlinedButton(
                    onPressed: _busy ? null : () => _act(a),
                    child: const Text('Submit to supplier'),
                  ),
            ]),
          ],
        ),
      ),
    );
  }
}

/// A delivery against one line — POST .../purchase-orders/{id}/receive/.
/// Over-receiving is refused by the API: a supplier who ships more than was
/// ordered has changed the order, and that is a decision on the order.
class _ReceiveForm extends StatefulWidget {
  final Map<String, dynamic> order;
  const _ReceiveForm({required this.order});

  @override
  State<_ReceiveForm> createState() => _ReceiveFormState();
}

class _ReceiveFormState extends State<_ReceiveForm> {
  final _quantity = TextEditingController();
  final _batch = TextEditingController();
  final _cost = TextEditingController();
  DateTime? _expiry;
  int? _lineId;
  bool _saving = false;
  String? _error;

  List<Map<String, dynamic>> get _openLines =>
      ((widget.order['lines'] as List?) ?? [])
          .cast<Map<String, dynamic>>()
          .where((l) => (l['outstanding'] as int? ?? 0) > 0)
          .toList();

  @override
  void initState() {
    super.initState();
    final open = _openLines;
    if (open.isNotEmpty) _lineId = open.first['id'] as int?;
  }

  @override
  void dispose() {
    _quantity.dispose();
    _batch.dispose();
    _cost.dispose();
    super.dispose();
  }

  Future<void> _pickExpiry() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(now.year + 1, now.month, now.day),
      firstDate: now,
      lastDate: DateTime(now.year + 15),
    );
    if (picked != null) setState(() => _expiry = picked);
  }

  Future<void> _submit() async {
    final quantity = int.tryParse(_quantity.text.trim()) ?? 0;
    if (_lineId == null || quantity <= 0 || _batch.text.trim().isEmpty) {
      setState(() =>
          _error = 'A delivery needs a line, a quantity and a batch number.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post(
        '/api/pharmacy/purchase-orders/${widget.order['id']}/receive/',
        {
          'line': _lineId,
          'quantity': quantity,
          'batch_number': _batch.text.trim(),
          if (_expiry != null)
            'expiry_date': _expiry!.toIso8601String().substring(0, 10),
          if (_cost.text.trim().isNotEmpty) 'unit_cost': _cost.text.trim(),
        },
      );
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
      title: 'Receive against ${widget.order['reference']}',
      saving: _saving,
      error: _error,
      submitLabel: 'Book in',
      onSubmit: _submit,
      children: [
        SearchableDropdown<int?>(
          initialValue: _lineId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Line'),
          items: [
            for (final l in _openLines)
              DropdownMenuItem(
                value: l['id'] as int,
                child: Text('${l['item_name']} — ${l['outstanding']} outstanding'),
              ),
          ],
          onChanged: (v) => setState(() => _lineId = v),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _quantity,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Quantity'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _batch,
              decoration: const InputDecoration(labelText: 'Batch number'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _cost,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
              labelText: 'Invoice unit cost (₦)',
              helperText: 'Leave blank to keep the ordered price'),
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Expiry'),
          subtitle: Text(_expiry == null
              ? 'Not set'
              : _expiry!.toIso8601String().substring(0, 10)),
          trailing: const Icon(Icons.event_outlined),
          onTap: _pickExpiry,
        ),
      ],
    );
  }
}

/// A new order: pick the supplier, then build the lines.
class _OrderForm extends StatefulWidget {
  const _OrderForm();

  @override
  State<_OrderForm> createState() => _OrderFormState();
}

class _OrderFormState extends State<_OrderForm> {
  final _quantity = TextEditingController(text: '1');
  final _cost = TextEditingController();
  final _notes = TextEditingController();
  final List<OrderLineDraft> _lines = [];
  List<Map<String, dynamic>> _suppliers = [];
  List<Map<String, dynamic>> _items = [];
  int? _supplierId;
  int? _itemId;
  DateTime? _expected;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final suppliers =
          await api.getList('/api/pharmacy/suppliers/', {'is_active': 'true'});
      final items = await loadStockItems();
      if (mounted) {
        setState(() {
          _suppliers = suppliers.cast<Map<String, dynamic>>();
          _items = items;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  void dispose() {
    _quantity.dispose();
    _cost.dispose();
    _notes.dispose();
    super.dispose();
  }

  void _addLine() {
    final item = _items.firstWhere((i) => i['id'] == _itemId,
        orElse: () => <String, dynamic>{});
    if (item.isEmpty) {
      setState(() => _error = 'Pick an item.');
      return;
    }
    final quantity = int.tryParse(_quantity.text.trim()) ?? 0;
    if (quantity <= 0) {
      setState(() => _error = 'Quantity must be at least 1.');
      return;
    }
    setState(() {
      _error = null;
      _lines.add(OrderLineDraft(
        itemId: item['id'] as int,
        name: '${item['name']}',
        quantity: quantity,
        // Default to what the item last cost, so a routine restock is two taps.
        unitCost: num.tryParse(_cost.text.trim())?.toDouble() ??
            num.tryParse('${item['cost_price']}')?.toDouble() ??
            0,
      ));
      _quantity.text = '1';
      _cost.clear();
    });
  }

  Future<void> _pickExpected() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now.add(const Duration(days: 7)),
      firstDate: now,
      lastDate: DateTime(now.year + 2),
    );
    if (picked != null) setState(() => _expected = picked);
  }

  Future<void> _submit() async {
    if (_supplierId == null) {
      setState(() => _error = 'Pick the supplier.');
      return;
    }
    if (_lines.isEmpty) {
      setState(() => _error = 'An order needs at least one line.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post(
        '/api/pharmacy/purchase-orders/',
        purchaseOrderBody(
          supplierId: _supplierId!,
          lines: _lines,
          expectedDate: _expected?.toIso8601String().substring(0, 10),
          notes: _notes.text,
        ),
      );
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
      title: 'New purchase order',
      saving: _saving,
      error: _error,
      submitLabel: 'Create order',
      onSubmit: _submit,
      children: [
        SearchableDropdown<int?>(
          initialValue: _supplierId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Supplier'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— select —')),
            for (final s in _suppliers)
              DropdownMenuItem(value: s['id'] as int, child: Text('${s['name']}')),
          ],
          onChanged: (v) => setState(() => _supplierId = v),
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Expected'),
          subtitle: Text(_expected == null
              ? 'Not set'
              : _expected!.toIso8601String().substring(0, 10)),
          trailing: const Icon(Icons.event_outlined),
          onTap: _pickExpected,
        ),
        const Divider(),
        SearchableDropdown<int?>(
          initialValue: _itemId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Item'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— select —')),
            for (final i in _items)
              DropdownMenuItem(
                value: i['id'] as int,
                child: Text('${i['name']} · cost ${money(i['cost_price'])}'),
              ),
          ],
          onChanged: (v) => setState(() => _itemId = v),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _quantity,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Quantity'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _cost,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Unit cost (₦)'),
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.tonal(onPressed: _addLine, child: const Text('Add')),
        ]),
        const SizedBox(height: 12),
        if (_lines.isEmpty)
          Text('No lines yet.',
              style: TextStyle(color: context.hintColor, fontSize: 13))
        else ...[
          for (var i = 0; i < _lines.length; i++)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(_lines[i].name,
                  style: TextStyle(color: context.labelColor, fontSize: 14)),
              subtitle: Text(
                  '${_lines[i].quantity} × ${money(_lines[i].unitCost)}'),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(money(_lines[i].lineCost),
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                IconButton(
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => setState(() => _lines.removeAt(i)),
                ),
              ]),
            ),
          Align(
            alignment: Alignment.centerRight,
            child: Text('Order value ${money(orderTotal(_lines))}',
                style: const TextStyle(
                    color: EnhancedTheme.primaryTeal,
                    fontWeight: FontWeight.w800)),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Notes'),
        ),
      ],
    );
  }
}
