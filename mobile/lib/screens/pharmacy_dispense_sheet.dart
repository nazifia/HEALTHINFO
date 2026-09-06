import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';
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
  final _number = TextEditingController();
  final List<BasketLine> _basket = [];
  List<Map<String, dynamic>> _items = [];
  List<Map<String, dynamic>> _enrollments = [];
  // Clearances this card already holds, and the one this sale spends. Only
  // usable ones are offered: an expired or already-spent approval is not.
  List<Map<String, dynamic>> _auths = [];
  // What the patient's number turned up, and which of it this sale fills.
  // Null until a lookup has run, which is not the same as an empty result.
  List<Map<String, dynamic>>? _orders;
  int? _fillingId;
  bool _finding = false;
  int? _itemId;
  int? _patientId;
  int? _enrollmentId;
  int? _authId;
  String _method = 'cash';
  bool _saving = false;
  bool _asking = false;
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
    _number.dispose();
    super.dispose();
  }

  /// What the number the patient handed over is still owed.
  ///
  /// Asks with ?undispensed=1, so what comes back is only what can still be
  /// handed over — here and, for an order written at another facility, there.
  /// The counter scripts also returned are left alone: those are dispensed off
  /// their own screen, line by line.
  Future<void> _find() async {
    final number = _number.text.trim();
    if (number.isEmpty) return;
    setState(() {
      _finding = true;
      _error = null;
    });
    try {
      final found = await api.get('/api/prescriptions/scripts/by-number/',
          {'number': number, 'undispensed': '1'});
      final body = (found as Map).cast<String, dynamic>();
      final here = ((body['orders'] ?? []) as List)
          .map((o) => {...(o as Map).cast<String, dynamic>(), 'facility': 'Here'});
      final elsewhere = ((body['orders_elsewhere'] ?? []) as List)
          .map((o) => (o as Map).cast<String, dynamic>());
      if (!mounted) return;
      setState(() {
        _orders = [...here, ...elsewhere];
        // A number the pharmacist has re-typed may not carry the old pick.
        if (!_orders!.any((o) => o['id'] == _fillingId)) _fillingId = null;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _orders = null;
          _fillingId = null;
          _error = '$e';
        });
      }
    } finally {
      if (mounted) setState(() => _finding = false);
    }
  }

  String _orderLabel(Map<String, dynamic> o) => [
        '${o['medication_name'] ?? ''}',
        '${o['dose'] ?? ''}',
        '${o['frequency'] ?? ''}',
        o['duration_days'] == null ? '' : '${o['duration_days']} days',
      ].where((p) => p.trim().isNotEmpty).join(' · ');

  Future<void> _loadItems() async {
    var rows = <Map<String, dynamic>>[];
    try {
      rows = await loadStockItems();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
    if (mounted) setState(() => _items = rows);
  }

  /// A patient's scheme cards. One card is picked for the pharmacist; two or
  /// more, and they say which one is being billed.
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
        setState(() {
          _enrollments = rows.cast<Map<String, dynamic>>();
          if (_enrollments.length == 1) {
            _enrollmentId = _enrollments.first['id'] as int?;
          }
        });
      }
    } catch (_) {
      // A missing card list is not a reason to block a cash sale.
    }
    await _loadAuths();
  }

  /// Clearances the picked card can still spend.
  ///
  /// Above the insurer's threshold the sale is refused without one, so the
  /// list is offered before the pharmacist finds that out at checkout.
  Future<void> _loadAuths() async {
    setState(() {
      _authId = null;
      _auths = [];
    });
    if (_enrollmentId == null) return;
    try {
      final rows = await api.getList('/api/pharmacy/pre-authorizations/',
          {'enrollment': '$_enrollmentId', 'status': 'approved'});
      if (mounted) {
        setState(() => _auths = rows
            .cast<Map<String, dynamic>>()
            .where((r) => r['is_usable'] == true)
            .toList());
      }
    } catch (_) {
      // The checkout still says what the insurer wants; an empty list here
      // only means none was found to offer.
    }
  }

  /// Raise the request without leaving the till.
  ///
  /// The ask is the basket itself, itemised, so the insurer can answer drug by
  /// drug. Nothing is dispensed on it yet: the answer arrives as an alert, and
  /// the clearance shows up here once it does.
  Future<void> _askInsurer() async {
    if (_enrollmentId == null) {
      setState(() => _error = "Pick the patient's scheme card first.");
      return;
    }
    final body = preauthBody(lines: _basket, enrollmentId: _enrollmentId!);
    if ((body['items'] as List).isEmpty) {
      setState(() => _error = 'Add the items first — the insurer is asked for '
          'a figure.');
      return;
    }
    setState(() {
      _asking = true;
      _error = null;
    });
    try {
      final auth = await api.post('/api/pharmacy/pre-authorizations/', body);
      if (mounted) {
        showSuccess(context,
            'Requested ${(auth as Map)['reference']} — it appears here once '
            'the insurer answers.');
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _asking = false);
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
          authorizationId: _authId,
          prescriptionId: _fillingId,
          patientNumber: _number.text,
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
        Row(children: [
          Expanded(
            child: TextField(
              controller: _number,
              keyboardType: TextInputType.phone,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _find(),
              decoration: const InputDecoration(
                labelText: "Patient's number (optional)",
                hintText: 'Phone or hospital number…',
              ),
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.tonal(
              onPressed: _finding ? null : _find,
              child: Text(_finding ? 'Finding…' : 'Find')),
        ]),
        if (_orders != null) ...[
          const SizedBox(height: 8),
          if (_orders!.isEmpty)
            Text('Nothing outstanding for that number.',
                style: TextStyle(color: context.hintColor, fontSize: 13))
          else
            // One order per sale: the API takes one, and the drugs written
            // with it are marked off by the basket lines that match them.
            RadioGroup<int?>(
              groupValue: _fillingId,
              onChanged: (v) => setState(() => _fillingId = v),
              child: Column(children: [
                for (final o in _orders!)
                  RadioListTile<int?>(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    value: o['id'] as int?,
                    title: Text(_orderLabel(o),
                        style:
                            TextStyle(color: context.labelColor, fontSize: 14)),
                    subtitle: Text('From ${o['facility'] ?? '—'}',
                        style:
                            TextStyle(color: context.hintColor, fontSize: 12)),
                  ),
              ]),
            ),
          if (_fillingId != null)
            Text('This sale fills that order — it is marked dispensed when the '
                'sale completes.',
                style: TextStyle(color: context.hintColor, fontSize: 12)),
        ],
        const SizedBox(height: 12),
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
            onChanged: (v) {
              setState(() => _enrollmentId = v);
              _loadAuths();
            },
          ),
          if (_patientId == null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('Pick the patient first to load their cards.',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            ),
          const SizedBox(height: 12),
          SearchableDropdown<int?>(
            initialValue: _authId,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Authorisation',
              helperText: "Only for a covered sale above the insurer's "
                  'threshold.',
            ),
            items: [
              const DropdownMenuItem(value: null, child: Text('— none —')),
              for (final a in _auths)
                DropdownMenuItem(
                  value: a['id'] as int,
                  child: Text('${a['reference']} · ${money(a['amount_approved'])}'
                      '${a['expires_on'] == null ? '' : ' · to ${a['expires_on']}'}'),
                ),
            ],
            onChanged: (v) => setState(() => _authId = v),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.tonal(
              onPressed: _asking ? null : _askInsurer,
              child: Text(_asking ? 'Asking…' : 'Ask the insurer'),
            ),
          ),
        ],
      ],
    );
  }
}
