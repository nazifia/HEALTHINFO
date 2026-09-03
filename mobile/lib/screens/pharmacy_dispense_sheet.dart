import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/searchable_dropdown.dart';
import 'pharmacy_stock_screen.dart' show loadStockItems;
import 'report_scaffold.dart';

/// The dispensing counter: build a basket, name the payer, hand it over.
///
/// The client never picks a batch or a price — POST /api/pharmacy/sales/
/// allocates first-expiry-first-out and prices the sale server-side. Pops the
/// created sale so the caller can show it (and its receipt) straight away.
class DispenseSheet extends StatefulWidget {
  const DispenseSheet({super.key});

  @override
  State<DispenseSheet> createState() => _DispenseSheetState();
}

class _DispenseSheetState extends State<DispenseSheet> {
  final _quantity = TextEditingController(text: '1');
  final _discount = TextEditingController(text: '0');
  final List<BasketLine> _basket = [];
  List<Map<String, dynamic>> _items = [];
  List<Map<String, dynamic>> _enrollments = [];
  int? _itemId;
  int? _patientId;
  int? _enrollmentId;
  String _method = 'cash';
  bool _saving = false;
  String? _error;

  bool get _insured => _method == 'hmo';

  @override
  void initState() {
    super.initState();
    _loadItems();
  }

  @override
  void dispose() {
    _quantity.dispose();
    _discount.dispose();
    super.dispose();
  }

  Future<void> _loadItems() async {
    var rows = <Map<String, dynamic>>[];
    try {
      rows = await loadStockItems();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
    if (mounted) setState(() => _items = rows);
  }

  /// A patient's scheme cards — an HMO sale needs the one they presented.
  Future<void> _loadEnrollments(int? patientId) async {
    setState(() {
      _enrollmentId = null;
      _enrollments = [];
    });
    if (patientId == null) return;
    try {
      final rows = await api.getList('/api/pharmacy/enrollments/',
          {'patient': '$patientId', 'is_active': 'true'});
      if (mounted) {
        setState(() => _enrollments = rows.cast<Map<String, dynamic>>());
      }
    } catch (_) {
      // A missing card list is not a reason to block a cash sale.
    }
  }

  void _add() {
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
      _basket.add(BasketLine(
        itemId: item['id'] as int,
        name: '${item['name']}',
        unitPrice: num.tryParse('${item['unit_price']}')?.toDouble() ?? 0,
        quantity: quantity,
        discount: num.tryParse(_discount.text.trim())?.toDouble() ?? 0,
      ));
      _quantity.text = '1';
      _discount.text = '0';
    });
  }

  Future<void> _submit() async {
    if (_basket.isEmpty) {
      setState(() => _error = 'Add at least one item.');
      return;
    }
    if (_insured && _enrollmentId == null) {
      setState(() => _error = 'An HMO sale needs the patient\'s scheme card.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final sale = await api.post(
        '/api/pharmacy/sales/',
        saleBody(
          lines: _basket,
          paymentMethod: _method,
          patientId: _patientId,
          enrollmentId: _enrollmentId,
        ),
      );
      if (mounted) Navigator.of(context).pop(sale as Map<String, dynamic>?);
    } catch (e) {
      // Out of stock, a lapsed card, a short batch — the API says which, and
      // nothing was dispensed, so the basket stays intact for a second try.
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: 'Dispense',
      saving: _saving,
      error: _error,
      submitLabel: 'Complete sale',
      onSubmit: _submit,
      children: [
        SearchableDropdown<int?>(
          initialValue: _itemId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Item'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— select —')),
            for (final i in _items)
              DropdownMenuItem(
                value: i['id'] as int,
                child: Text('${i['name']} · ${money(i['unit_price'])}'
                    ' (${units(i['quantity_on_hand'])} left)'),
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
              controller: _discount,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Discount (₦)'),
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.tonal(onPressed: _add, child: const Text('Add')),
        ]),
        const SizedBox(height: 12),
        if (_basket.isEmpty)
          Text('Nothing added yet.',
              style: TextStyle(color: context.hintColor, fontSize: 13))
        else ...[
          for (var i = 0; i < _basket.length; i++)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(_basket[i].name,
                  style: TextStyle(color: context.labelColor, fontSize: 14)),
              subtitle: Text(
                  '${_basket[i].quantity} × ${money(_basket[i].unitPrice)}'),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(money(_basket[i].lineTotal),
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                IconButton(
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => setState(() => _basket.removeAt(i)),
                ),
              ]),
            ),
          Align(
            alignment: Alignment.centerRight,
            child: Text('Estimated total ${money(basketTotal(_basket))}',
                style: TextStyle(
                    color: EnhancedTheme.primaryTeal,
                    fontWeight: FontWeight.w800)),
          ),
        ],
        const SizedBox(height: 12),
        PatientPicker(
          onChanged: (id) {
            _patientId = id;
            _loadEnrollments(id);
          },
        ),
        const SizedBox(height: 12),
        SearchableDropdown<String>(
          initialValue: _method,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Payment'),
          items: const [
            DropdownMenuItem(value: 'cash', child: Text('Cash')),
            DropdownMenuItem(value: 'card', child: Text('Card')),
            DropdownMenuItem(value: 'transfer', child: Text('Transfer')),
            DropdownMenuItem(value: 'hmo', child: Text('HMO / scheme')),
          ],
          onChanged: (v) => setState(() => _method = v ?? 'cash'),
        ),
        if (_insured) ...[
          const SizedBox(height: 12),
          SearchableDropdown<int?>(
            initialValue: _enrollmentId,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Scheme card'),
            items: [
              const DropdownMenuItem(value: null, child: Text('— select —')),
              for (final e in _enrollments)
                DropdownMenuItem(
                  value: e['id'] as int,
                  child: Text('${e['hmo_name']} · ${e['member_number']}'
                      ' (${e['effective_coverage']}%)'),
                ),
            ],
            onChanged: (v) => setState(() => _enrollmentId = v),
          ),
          if (_patientId == null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('Pick the patient first to load their cards.',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            ),
        ],
      ],
    );
  }
}
