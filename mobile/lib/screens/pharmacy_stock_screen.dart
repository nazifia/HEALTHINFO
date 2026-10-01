import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'report_scaffold.dart';

/// Every active stock item, paged through.
///
/// A picker that stops at the first 25 items is a picker the counter cannot
/// sell from, and an order form that cannot see an item cannot restock it.
/// ponytail: capped at 10 pages; past ~250 items this wants a search field.
Future<List<Map<String, dynamic>>> loadStockItems() async {
  final rows = <Map<String, dynamic>>[];
  for (var page = 1; page <= 10; page++) {
    final batch = await api.getList('/api/pharmacy/items/', {
      'is_active': 'true',
      'page': '$page',
    });
    rows.addAll(batch.cast<Map<String, dynamic>>());
    if (batch.length < 25) break;
  }
  return rows;
}

/// Stock items — GET /api/pharmacy/items/.
///
/// Staff read the list and book deliveries in; only the pharmacy admin adds an
/// item or moves a price, and only the admin corrects a batch (both gated in
/// the API too, so hiding a button is convenience, not the control).
class PharmacyStockScreen extends StatelessWidget {
  const PharmacyStockScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final role = snap.data;
        final admin = isPharmacyAdmin(role);
        return ReportListScreen(
          path: '/api/pharmacy/items/',
          searchHint: 'Search items…',
          fabLabel: 'Add item',
          showFab: admin,
          emptyIcon: Icons.inventory_2_outlined,
          emptyTitle: 'No stock items yet',
          emptyMessage: admin
              ? 'Tap "Add item" to start the item list.'
              : 'The pharmacy admin sets up the item list.',
          savedMessage: 'Item saved.',
          filters: const [
            ReportFilter(
              param: 'form',
              anyLabel: 'Any form',
              options: {
                'tablet': 'Tablet',
                'capsule': 'Capsule',
                'syrup': 'Syrup',
                'injection': 'Injection',
                'cream': 'Cream',
                'drops': 'Drops',
                'consumable': 'Consumable',
                'other': 'Other',
              },
            ),
            ReportFilter(
              param: 'is_active',
              anyLabel: 'Any state',
              options: {'true': 'Active', 'false': 'Retired'},
            ),
          ],
          header: (items) => _Header(items: items),
          card: (row, reload, edit) =>
              _ItemCard(row: row, admin: admin, edit: edit, reload: reload),
          onTap: (row) => _openItem(context, row),
          form: (existing) => _ItemForm(existing: existing),
        );
      },
    );
  }

  static Future<void> _openItem(
    BuildContext context,
    Map<String, dynamic> row,
  ) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ItemSheet(item: row),
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final low = items.where((r) => r['is_low_stock'] == true).length;
    final onHand = items.fold<num>(
      0,
      (sum, r) => sum + ((r['quantity_on_hand'] as num?) ?? 0),
    );
    final retail = items.fold<num>(0, (sum, r) {
      final price = num.tryParse('${r['unit_price']}') ?? 0;
      return sum + price * ((r['quantity_on_hand'] as num?) ?? 0);
    });
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.inventory_2_outlined,
            title: 'Stock',
            subtitle: '${items.length} item${items.length == 1 ? '' : 's'}',
            color: EnhancedTheme.primaryTeal,
          ),
          KpiRow(
            tiles: [
              KpiTile(
                icon: Icons.warning_amber_rounded,
                label: 'To reorder',
                value: '$low',
                color: EnhancedTheme.errorRed,
              ),
              KpiTile(
                icon: Icons.medication_outlined,
                label: 'Units on hand',
                value: units(onHand),
                color: EnhancedTheme.primaryTeal,
              ),
              KpiTile(
                icon: Icons.sell_outlined,
                label: 'At retail',
                value: money(retail),
                color: EnhancedTheme.accentOrange,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ItemCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  final VoidCallback reload;
  const _ItemCard({
    required this.row,
    required this.admin,
    required this.edit,
    required this.reload,
  });

  /// Tap-to-edit one number on the card — PATCH /api/pharmacy/items/{id}/
  /// with just that field. Admin only (the API refuses anyone else).
  Future<void> _editField(
    BuildContext context,
    String field,
    String label, {
    bool integer = false,
  }) async {
    final controller = TextEditingController(text: '${row[field] ?? ''}');
    final value = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(label),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.numberWithOptions(decimal: !integer),
          onSubmitted: (v) => Navigator.of(ctx).pop(v.trim()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (value == null || value.isEmpty || value == '${row[field]}') return;
    // Quantity on hand is a sum over batches: send the typed count as the
    // difference and the API books a receipt or a FIFO adjustment for it.
    final Map<String, dynamic> body;
    if (field == 'quantity_on_hand') {
      final counted = int.tryParse(value);
      if (counted == null || counted < 0) {
        if (context.mounted) showError(context, 'Enter a whole number, 0 or more.');
        return;
      }
      body = {'add_stock': counted - ((row[field] as num?)?.toInt() ?? 0)};
    } else {
      body = {field: value};
    }
    try {
      await api.patch('/api/pharmacy/items/${row['id']}/', body);
      reload();
      if (context.mounted) showSuccess(context, '$label saved.');
    } catch (e) {
      if (context.mounted) showError(context, '$e');
    }
  }

  /// A number the admin can tap to change; plain text for everyone else.
  Widget _editable(BuildContext context, Widget child, VoidCallback onTap) =>
      admin
          ? InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(6),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(child: child),
                  const SizedBox(width: 4),
                  Icon(Icons.edit, size: 12, color: context.hintColor),
                ],
              ),
            )
          : child;

  @override
  Widget build(BuildContext context) {
    final low = row['is_low_stock'] == true;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${row['name']}',
                  style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
              ),
              if (low)
                const ReportBadge(
                  text: 'reorder',
                  color: EnhancedTheme.errorRed,
                ),
              if (admin)
                IconButton(
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  onPressed: edit,
                ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 16,
            children: [
              _editable(
                context,
                Text(
                  '${units(row['quantity_on_hand'])} ${row['unit']}(s) on hand',
                  style: TextStyle(color: context.hintColor, fontSize: 13),
                ),
                () => _editField(
                  context,
                  'quantity_on_hand',
                  'Quantity on hand',
                  integer: true,
                ),
              ),
              _editable(
                context,
                Text(
                  'reorder at ${units(row['reorder_level'])}',
                  style: TextStyle(color: context.hintColor, fontSize: 13),
                ),
                () => _editField(
                  context,
                  'reorder_level',
                  'Reorder level',
                  integer: true,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 16,
            children: [
              _editable(
                context,
                Text(
                  '${money(row['unit_price'])} each',
                  style: const TextStyle(
                    color: EnhancedTheme.primaryTeal,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                () => _editField(context, 'unit_price', 'Sell price'),
              ),
              if (admin)
                _editable(
                  context,
                  Text(
                    'cost ${money(row['cost_price'])}',
                    style: TextStyle(color: context.hintColor, fontSize: 13),
                  ),
                  () => _editField(context, 'cost_price', 'Cost price'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// An item's batches, with the two ways stock legitimately moves outside a
/// sale: booking a delivery in, and correcting a count.
class _ItemSheet extends StatefulWidget {
  final Map<String, dynamic> item;
  const _ItemSheet({required this.item});

  @override
  State<_ItemSheet> createState() => _ItemSheetState();
}

class _ItemSheetState extends State<_ItemSheet> {
  late Future<List<dynamic>> _batches;
  String? _role;

  @override
  void initState() {
    super.initState();
    _reload();
    api.myRole().then((r) {
      if (mounted) setState(() => _role = r);
    });
  }

  void _reload() => setState(() {
    _batches = api.getList('/api/pharmacy/batches/', {
      'item': '${widget.item['id']}',
    });
  });

  Future<void> _receive() async {
    final booked = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ReceiveForm(item: widget.item),
    );
    if (booked == true) {
      _reload();
      if (mounted) showSuccess(context, 'Stock received.');
    }
  }

  Future<void> _editBatch(Map<String, dynamic> batch) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ReceiveForm(item: widget.item, batch: batch),
    );
    if (saved == true) {
      _reload();
      if (mounted) showSuccess(context, 'Batch updated.');
    }
  }

  Future<void> _adjust(Map<String, dynamic> batch) async {
    final done = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AdjustForm(batch: batch),
    );
    if (done == true) {
      _reload();
      if (mounted) showSuccess(context, 'Stock adjusted.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final admin = isPharmacyAdmin(_role);
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
            Text(
              '${widget.item['name']}',
              style: TextStyle(
                color: context.labelColor,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            Text(
              '${money(widget.item['unit_price'])} each',
              style: TextStyle(color: context.hintColor, fontSize: 13),
            ),
            const SizedBox(height: 16),
            FutureBuilder<List<dynamic>>(
              future: _batches,
              builder: (context, snap) {
                if (snap.connectionState == ConnectionState.waiting) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Center(
                      child: CircularProgressIndicator(
                        color: EnhancedTheme.primaryTeal,
                      ),
                    ),
                  );
                }
                final rows = (snap.data ?? []).cast<Map<String, dynamic>>();
                if (rows.isEmpty) {
                  return Text(
                    'No batches on the shelf.',
                    style: TextStyle(color: context.hintColor, fontSize: 13),
                  );
                }
                return Column(
                  children: [
                    for (final b in rows)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        onTap: () => _editBatch(b),
                        title: Text(
                          'Batch ${b['batch_number']}',
                          style: TextStyle(
                            color: context.labelColor,
                            fontSize: 14,
                          ),
                        ),
                        subtitle: Text(
                          [
                            '${units(b['quantity'])} left',
                            if (b['expiry_date'] != null)
                              'expires ${b['expiry_date']}',
                            if ((b['supplier_name'] ?? '')
                                .toString()
                                .isNotEmpty)
                              '${b['supplier_name']}',
                          ].join(' · '),
                        ),
                        trailing: b['is_expired'] == true
                            ? const ReportBadge(
                                text: 'expired',
                                color: EnhancedTheme.errorRed,
                              )
                            : admin
                            ? TextButton(
                                onPressed: () => _adjust(b),
                                child: const Text('Adjust'),
                              )
                            : null,
                      ),
                  ],
                );
              },
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _receive,
                style: FilledButton.styleFrom(
                  backgroundColor: EnhancedTheme.primaryTeal,
                ),
                icon: const Icon(Icons.local_shipping_outlined),
                label: const Text('Receive delivery'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Booking a consignment in — POST /api/pharmacy/items/{id}/receive/ — or,
/// given [batch], correcting its details — PATCH /api/pharmacy/batches/{id}/.
/// The quantity is never edited here: it moves through receipts, sales and
/// adjustments only, so the ledger keeps explaining the shelf.
class _ReceiveForm extends StatefulWidget {
  final Map<String, dynamic> item;
  final Map<String, dynamic>? batch;
  const _ReceiveForm({required this.item, this.batch});

  @override
  State<_ReceiveForm> createState() => _ReceiveFormState();
}

class _ReceiveFormState extends State<_ReceiveForm> {
  final _quantity = TextEditingController();
  final _batch = TextEditingController();
  final _cost = TextEditingController();
  DateTime? _expiry;
  List<Map<String, dynamic>> _suppliers = [];
  int? _supplierId;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.batch != null;

  @override
  void initState() {
    super.initState();
    final b = widget.batch;
    if (b != null) {
      _batch.text = '${b['batch_number'] ?? ''}';
      _cost.text = '${b['cost_price'] ?? ''}';
      _expiry = DateTime.tryParse('${b['expiry_date']}');
      _supplierId = b['supplier'] as int?;
    }
    _loadSuppliers();
  }

  /// A supplier is optional on a receipt, so a failed list must not stop one
  /// being booked in.
  Future<void> _loadSuppliers() async {
    try {
      final rows = await api.getAll('/api/pharmacy/suppliers/', {
        'is_active': 'true',
      });
      if (mounted) {
        setState(() => _suppliers = rows.cast<Map<String, dynamic>>());
      }
    } catch (_) {}
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
      initialDate: _expiry ?? DateTime(now.year + 1, now.month, now.day),
      // An edit may be recording a date already past.
      firstDate: _isEdit ? DateTime(now.year - 15) : now,
      lastDate: DateTime(now.year + 15),
    );
    if (picked != null) setState(() => _expiry = picked);
  }

  Future<void> _submit() async {
    final quantity = int.tryParse(_quantity.text.trim()) ?? 0;
    if (_isEdit && _batch.text.trim().isEmpty) {
      setState(() => _error = 'A batch needs a batch number.');
      return;
    }
    if (!_isEdit && (quantity <= 0 || _batch.text.trim().isEmpty)) {
      setState(
        () => _error = 'A delivery needs a quantity and a batch number.',
      );
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      if (_isEdit) {
        await api.patch('/api/pharmacy/batches/${widget.batch!['id']}/', {
          'batch_number': _batch.text.trim(),
          'expiry_date': _expiry?.toIso8601String().substring(0, 10),
          'cost_price': _cost.text.trim().isEmpty ? '0' : _cost.text.trim(),
          'supplier': _supplierId,
        });
        if (mounted) Navigator.of(context).pop(true);
        return;
      }
      await api.post('/api/pharmacy/items/${widget.item['id']}/receive/', {
        'quantity': quantity,
        'batch_number': _batch.text.trim(),
        if (_expiry != null)
          'expiry_date': _expiry!.toIso8601String().substring(0, 10),
        if (_cost.text.trim().isNotEmpty) 'cost_price': _cost.text.trim(),
        if (_supplierId != null) 'supplier': _supplierId,
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
      title: _isEdit
          ? 'Edit batch ${widget.batch!['batch_number']}'
          : 'Receive ${widget.item['name']}',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Book in',
      onSubmit: _submit,
      children: [
        Row(
          children: [
            if (!_isEdit) ...[
              Expanded(
                child: TextField(
                  controller: _quantity,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Quantity'),
                ),
              ),
              const SizedBox(width: 12),
            ],
            Expanded(
              child: TextField(
                controller: _batch,
                decoration: const InputDecoration(labelText: 'Batch number'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _cost,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Unit cost (₦)'),
        ),
        const SizedBox(height: 12),
        SearchableDropdown<int?>(
          initialValue: _supplierId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Supplier'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— none —')),
            for (final s in _suppliers)
              DropdownMenuItem(
                value: s['id'] as int,
                child: Text('${s['name']}'),
              ),
          ],
          onChanged: (v) => setState(() => _supplierId = v),
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Expiry'),
          subtitle: Text(
            _expiry == null
                ? 'Not set'
                : _expiry!.toIso8601String().substring(0, 10),
          ),
          trailing: const Icon(Icons.event_outlined),
          onTap: _pickExpiry,
        ),
      ],
    );
  }
}

/// A counted quantity and why it differs — POST /api/pharmacy/batches/{id}/adjust/.
class _AdjustForm extends StatefulWidget {
  final Map<String, dynamic> batch;
  const _AdjustForm({required this.batch});

  @override
  State<_AdjustForm> createState() => _AdjustFormState();
}

class _AdjustFormState extends State<_AdjustForm> {
  late final TextEditingController _quantity = TextEditingController(
    text: '${widget.batch['quantity'] ?? 0}',
  );
  final _reason = TextEditingController();
  bool _writeOff = false;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _quantity.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_reason.text.trim().isEmpty) {
      setState(() => _error = 'Say why the count differs.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post('/api/pharmacy/batches/${widget.batch['id']}/adjust/', {
        'quantity': int.tryParse(_quantity.text.trim()) ?? 0,
        'reason': _reason.text.trim(),
        'write_off': _writeOff,
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
      title: 'Adjust batch ${widget.batch['batch_number']}',
      saving: _saving,
      error: _error,
      submitLabel: 'Save count',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _quantity,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Counted quantity'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _reason,
          decoration: const InputDecoration(labelText: 'Reason'),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Write-off'),
          subtitle: const Text(
            'Expired, damaged or lost — not a count correction',
          ),
          value: _writeOff,
          onChanged: (v) => setState(() => _writeOff = v),
        ),
      ],
    );
  }
}

/// The item itself — admin only, and the API enforces that too.
class _ItemForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _ItemForm({this.existing});

  @override
  State<_ItemForm> createState() => _ItemFormState();
}

class _ItemFormState extends State<_ItemForm> {
  final _name = TextEditingController();
  final _unit = TextEditingController(text: 'unit');
  final _price = TextEditingController(text: '0');
  final _cost = TextEditingController(text: '0');
  final _reorder = TextEditingController(text: '0');
  final _addStock = TextEditingController();
  final _brand = TextEditingController();
  final _barcode = TextEditingController();
  final _markup = TextEditingController();
  List<Map<String, dynamic>> _branches = [];
  int? _branchId;
  String _form = 'tablet';
  String _store = 'retail';
  bool _prescriptionOnly = false;
  bool _isControlled = false;
  bool _isActive = true;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _name.text = '${e['name'] ?? ''}';
      _unit.text = '${e['unit'] ?? 'unit'}';
      _price.text = '${e['unit_price'] ?? 0}';
      _cost.text = '${e['cost_price'] ?? 0}';
      _reorder.text = '${e['reorder_level'] ?? 0}';
      _brand.text = '${e['brand'] ?? ''}';
      _barcode.text = '${e['barcode'] ?? ''}';
      _markup.text = '${e['markup'] ?? ''}';
      _branchId = e['branch'] as int?;
      _form = '${e['form'] ?? 'tablet'}';
      _store = '${e['store'] ?? 'retail'}';
      _isActive = e['is_active'] != false;
      _prescriptionOnly = e['prescription_only'] == true;
      _isControlled = e['is_controlled'] == true;
    }
    _loadBranches();
    _markup.addListener(_reprice);
    _cost.addListener(_reprice);
  }

  /// The sell price follows markup and cost as they are typed — the same
  /// figure the server would set from them.
  void _reprice() {
    final cost = double.tryParse(_cost.text.trim());
    final markup = double.tryParse(_markup.text.trim());
    if (cost == null || markup == null || markup <= 0) return;
    final price = (cost * (100 + markup) / 100).toStringAsFixed(2);
    if (_price.text != price) _price.text = price;
  }

  /// Branch is optional (blank means tenant-wide), so a failed list must not
  /// stop the item saving.
  Future<void> _loadBranches() async {
    try {
      final rows = await api.getAll('/api/branches/');
      if (mounted) {
        setState(() => _branches = rows.cast<Map<String, dynamic>>());
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _name.dispose();
    _unit.dispose();
    _price.dispose();
    _cost.dispose();
    _reorder.dispose();
    _addStock.dispose();
    _brand.dispose();
    _barcode.dispose();
    _markup.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Name the item.');
      return;
    }
    final added = int.tryParse(_addStock.text.trim()) ?? 0;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'brand': _brand.text.trim(),
        'barcode': _barcode.text.trim(),
        'branch': _branchId,
        // On create it prices the item only while the sell price is 0; on
        // an edit a changed markup or cost re-prices it from cost.
        if (_markup.text.trim().isNotEmpty) 'markup': _markup.text.trim(),
        'form': _form,
        'store': _store,
        'is_active': _isActive,
        'unit': _unit.text.trim().isEmpty ? 'unit' : _unit.text.trim(),
        'unit_price': _price.text.trim(),
        'cost_price': _cost.text.trim(),
        'reorder_level': int.tryParse(_reorder.text.trim()) ?? 0,
        'add_stock': added,
        'prescription_only': _prescriptionOnly,
        'is_controlled': _isControlled,
      };
      if (_isEdit) {
        await api.patch('/api/pharmacy/items/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pharmacy/items/', body);
      }
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
      title: _isEdit ? 'Edit item' : 'New item',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add item',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _brand,
          decoration: const InputDecoration(labelText: 'Brand'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _barcode,
          decoration: const InputDecoration(labelText: 'Barcode'),
        ),
        const SizedBox(height: 12),
        SearchableDropdown<int?>(
          initialValue: _branchId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Branch'),
          items: [
            const DropdownMenuItem(value: null, child: Text('All branches')),
            for (final b in _branches)
              DropdownMenuItem(
                value: b['id'] as int,
                child: Text('${b['name']}'),
              ),
          ],
          onChanged: (v) => setState(() => _branchId = v),
        ),
        const SizedBox(height: 12),
        SearchableDropdown<String>(
          initialValue: _store,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Store'),
          items: const [
            DropdownMenuItem(value: 'retail', child: Text('Retail')),
            DropdownMenuItem(value: 'wholesale', child: Text('Wholesale')),
          ],
          onChanged: (v) => setState(() => _store = v ?? 'retail'),
        ),
        const SizedBox(height: 12),
        SearchableDropdown<String>(
          initialValue: _form,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Form'),
          items: const [
            DropdownMenuItem(value: 'tablet', child: Text('Tablet')),
            DropdownMenuItem(value: 'capsule', child: Text('Capsule')),
            DropdownMenuItem(value: 'syrup', child: Text('Syrup')),
            DropdownMenuItem(value: 'injection', child: Text('Injection')),
            DropdownMenuItem(value: 'cream', child: Text('Cream')),
            DropdownMenuItem(value: 'drops', child: Text('Drops')),
            DropdownMenuItem(value: 'consumable', child: Text('Consumable')),
            DropdownMenuItem(value: 'other', child: Text('Other')),
          ],
          onChanged: (v) => setState(() => _form = v ?? 'tablet'),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _price,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Sell price (₦)'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _cost,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Cost (₦)'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _markup,
          keyboardType: TextInputType.number,
          decoration: InputDecoration(
            labelText: 'Markup (%)',
            helperText: _isEdit
                ? 'Changing markup or cost re-prices from cost.'
                : 'Sets the sell price from cost when sell price is 0.',
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _unit,
                decoration: const InputDecoration(labelText: 'Unit'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _reorder,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Reorder level'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _addStock,
          keyboardType: const TextInputType.numberWithOptions(signed: true),
          decoration: InputDecoration(
            labelText: _isEdit ? 'Add or remove stock' : 'Opening stock',
            helperText: _isEdit
                ? 'Now ${units(widget.existing!['quantity_on_hand'])} on hand; a positive number adds, a negative one removes (e.g. -5).'
                : 'Units on the shelf now.',
          ),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Prescription only'),
          value: _prescriptionOnly,
          onChanged: (v) => setState(() => _prescriptionOnly = v),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Controlled (poison)'),
          subtitle: const Text(
            'Counted in the state controlled-drug register.',
          ),
          value: _isControlled,
          onChanged: (v) => setState(() => _isControlled = v),
        ),
        if (_isEdit)
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Active'),
            subtitle: const Text('Off retires the item from sale and pickers.'),
            value: _isActive,
            onChanged: (v) => setState(() => _isActive = v),
          ),
      ],
    );
  }
}
