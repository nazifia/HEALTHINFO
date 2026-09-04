import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Prescriptions — GET /api/prescriptions/.
///
/// The counter's script: a named prescriber, a list of drugs, and a line-by-
/// line record of what has actually been handed over. Status is never set by
/// hand — it follows the lines, because "partly dispensed" is a fact about
/// which drugs went out, not a flag someone remembers to tick.
class PrescriptionsScreen extends StatelessWidget {
  const PrescriptionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final role = snap.data;
        return ReportListScreen(
          path: '/api/prescriptions/',
          searchHint: 'Patient, phone, doctor or diagnosis…',
          fabLabel: 'Write up a script',
          showFab: isPharmacyStaff(role),
          emptyIcon: Icons.description_outlined,
          emptyTitle: 'No scripts yet',
          emptyMessage: 'Write up the paper script and dispense off it.',
          savedMessage: 'Prescription saved.',
          filters: const [
            ReportFilter(param: 'status', anyLabel: 'Any state', options: {
              'pending': 'Pending',
              'partial': 'Part-filled',
              'dispensed': 'Dispensed',
              'cancelled': 'Cancelled',
            }),
            ReportFilter(param: 'source', anyLabel: 'Any source', options: {
              'pharmacy': 'Written here',
              'portal': 'Sent in',
            }),
          ],
          card: (row, reload, edit) => _RxCard(row: row),
          onTap: (row) => _open(context, row, role),
          form: (existing) => const _RxForm(),
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
      builder: (_) => RxSheet(rx: row, role: role),
    );
  }
}

class _RxCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _RxCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final lines = ((row['lines'] ?? []) as List).cast<Map<String, dynamic>>();
    final out = lines.where((l) => l['is_dispensed'] == true).length;
    final prescriber =
        '${row['prescriber_name'] ?? row['doctor_name'] ?? 'No prescriber'}';
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['customer_name']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: statusColor(row['status'])),
        ]),
        const SizedBox(height: 4),
        Text('Rx${row['id']} · $prescriber',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        const SizedBox(height: 4),
        Text('$out of ${lines.length} line(s) dispensed',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if ((num.tryParse('${row['consultation_fee']}') ?? 0) > 0)
          Text(
              'Consultation ${row['consultation_category']} · '
              '${money(row['consultation_fee'])}',
              style: const TextStyle(
                  color: EnhancedTheme.accentCyan,
                  fontSize: 12,
                  fontWeight: FontWeight.w600)),
      ]),
    );
  }
}

/// One script in full: every line, and the tick that hands it over.
class RxSheet extends StatefulWidget {
  final Map<String, dynamic> rx;
  final String? role;
  const RxSheet({super.key, required this.rx, this.role});

  @override
  State<RxSheet> createState() => _RxSheetState();
}

class _RxSheetState extends State<RxSheet> {
  late Map<String, dynamic> _rx = widget.rx;
  // Lines the dispenser has ticked but not yet sent. Empty means "all of what
  // is still open", which is what the API does with an empty list.
  final Set<int> _picked = {};
  bool _busy = false;

  Future<void> _refresh() async {
    final fresh = await api.get('/api/prescriptions/${_rx['id']}/');
    if (mounted) {
      setState(() {
        _rx = (fresh as Map).cast<String, dynamic>();
        _picked.clear();
      });
    }
  }

  Future<void> _act(String action) async {
    setState(() => _busy = true);
    await runAction(
      context,
      '/api/prescriptions/${_rx['id']}/$action/',
      body: action == 'dispense' && _picked.isNotEmpty
          ? {'lines': _picked.toList()}
          : null,
      after: _refresh,
    );
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final lines = ((_rx['lines'] ?? []) as List).cast<Map<String, dynamic>>();
    final actions = rxActions('${_rx['status']}', widget.role);
    return Container(
      constraints:
          BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
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
              child: Text('${_rx['customer_name']}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
            ),
            ReportBadge(
                text: '${_rx['status']}', color: statusColor(_rx['status'])),
          ]),
          Text(
              'Rx${_rx['id']} · '
              '${_rx['prescriber_name'] ?? _rx['doctor_name'] ?? 'No prescriber'}',
              style: TextStyle(color: context.hintColor, fontSize: 13)),
          if ('${_rx['diagnosis'] ?? ''}'.trim().isNotEmpty)
            Text('${_rx['diagnosis']}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
          if ((num.tryParse('${_rx['consultation_fee']}') ?? 0) > 0) ...[
            const SizedBox(height: 8),
            FactRow('Consultation ${_rx['consultation_category']}',
                money(_rx['consultation_fee'])),
          ],
          const Divider(),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: lines.length,
              itemBuilder: (context, i) {
                final l = lines[i];
                final done = l['is_dispensed'] == true;
                final id = l['id'] as int;
                return CheckboxListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  value: done || _picked.contains(id),
                  // A dispensed line cannot be un-dispensed: the drug is gone.
                  onChanged: done || actions.isEmpty
                      ? null
                      : (v) => setState(() =>
                          v == true ? _picked.add(id) : _picked.remove(id)),
                  title: Text('${l['name']} ×${l['quantity']} ${l['unit']}',
                      style: TextStyle(
                          color: context.labelColor,
                          fontSize: 14,
                          decoration: done ? TextDecoration.lineThrough : null)),
                  subtitle: Text(
                    [
                      if ('${l['dosage'] ?? ''}'.isNotEmpty) '${l['dosage']}',
                      if ('${l['duration'] ?? ''}'.isNotEmpty)
                        '${l['duration']}',
                      if ('${l['instructions'] ?? ''}'.isNotEmpty)
                        '${l['instructions']}',
                    ].join(' · '),
                    style: TextStyle(color: context.hintColor, fontSize: 12),
                  ),
                );
              },
            ),
          ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: LinearProgressIndicator(minHeight: 2),
            )
          else ...[
            if (actions.contains('dispense'))
              Text(
                  _picked.isEmpty
                      ? 'Dispensing with nothing ticked hands over every open line.'
                      : '${_picked.length} line(s) ticked.',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            ActionRow(actions: actions, onAction: _act),
          ],
        ],
      ),
    );
  }
}

/// Write up a paper script: who it is for, who wrote it, and the drugs on it.
class _RxForm extends StatefulWidget {
  const _RxForm();

  @override
  State<_RxForm> createState() => _RxFormState();
}

class _RxFormState extends State<_RxForm> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _diagnosis = TextEditingController();
  final _lines = <RxLineDraft>[];
  Map<String, dynamic>? _prescriber;
  Map<String, dynamic>? _customer;
  String _category = '';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _diagnosis.dispose();
    super.dispose();
  }

  Future<void> _pickPrescriber() async {
    final row = await pickRow(
      context,
      path: '/api/prescriptions/prescribers/',
      title: 'Who wrote it?',
      hint: 'Name, licence or clinic…',
      label: (r) => '${r['name']}',
      subtitle: (r) => [
        '${r['license_number'] ?? ''}',
        '${r['hospital_name'] ?? r['clinic'] ?? ''}',
      ].where((v) => v.trim().isNotEmpty).join(' · '),
    );
    if (row != null) setState(() => _prescriber = row);
  }

  Future<void> _pickCustomer() async {
    final row = await pickRow(
      context,
      path: '/api/customers/',
      title: 'Who is it for?',
      hint: 'Name or phone…',
      label: (r) => '${r['name']}',
      subtitle: (r) => '${r['phone'] ?? ''}',
    );
    if (row == null) return;
    setState(() {
      _customer = row;
      _name.text = '${row['name']}';
      _phone.text = '${row['phone'] ?? ''}';
    });
  }

  Future<void> _addLine() async {
    final item = await pickRow(
      context,
      path: '/api/inventory/items/',
      title: 'Add a drug',
      hint: 'Drug name or brand…',
      label: (r) => '${r['name']}',
      subtitle: (r) =>
          '${r['brand'] ?? ''} · ${money(r['unit_price'])} · '
          '${r['quantity_on_hand'] ?? 0} in stock',
    );
    if (item == null || !mounted) return;
    final line = await showDialog<RxLineDraft>(
      context: context,
      builder: (_) => _LineDialog(item: item),
    );
    if (line != null) setState(() => _lines.add(line));
  }

  Future<void> _submit() async {
    if (_lines.isEmpty) {
      setState(() => _error = 'A script needs at least one drug on it.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post(
        '/api/prescriptions/',
        prescriptionBody(
          customerName: _name.text,
          customerPhone: _phone.text,
          lines: _lines,
          prescriberId: _prescriber?['id'] as int?,
          customerId: _customer?['id'] as int?,
          diagnosis: _diagnosis.text,
          consultationCategory: _category,
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
    final fee = _prescriber == null
        ? 0.0
        : consultationFee(_prescriber!, _category);
    return ReportFormSheet(
      title: 'Write up a script',
      saving: _saving,
      error: _error,
      submitLabel: 'Save script',
      onSubmit: _submit,
      children: [
        Row(children: [
          Expanded(
            child: TextField(
              controller: _name,
              decoration: const InputDecoration(
                  labelText: 'Patient name', hintText: 'Walk-in'),
            ),
          ),
          TextButton(onPressed: _pickCustomer, child: const Text('Find')),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(labelText: 'Phone (optional)'),
        ),
        const SizedBox(height: 12),
        InputDecorator(
          decoration: const InputDecoration(labelText: 'Prescriber'),
          child: Row(children: [
            Expanded(
              child: Text(
                _prescriber == null
                    ? 'Not linked'
                    : '${_prescriber!['name']}',
                style: TextStyle(
                    color: _prescriber == null
                        ? context.hintColor
                        : context.labelColor),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            TextButton(
                onPressed: _pickPrescriber,
                child: Text(_prescriber == null ? 'Link' : 'Change')),
          ]),
        ),
        const SizedBox(height: 12),
        // The band the doctor prices; the server snapshots the fee, so what is
        // shown here is a preview, never what gets charged.
        DropdownButtonFormField<String>(
          initialValue: _category.isEmpty ? null : _category,
          decoration: InputDecoration(
            labelText: 'Consultation band (optional)',
            helperText: fee > 0 ? 'Charges ${money(fee)} at the till' : null,
          ),
          items: const [
            DropdownMenuItem(value: '', child: Text('None')),
            DropdownMenuItem(value: 'A', child: Text('A')),
            DropdownMenuItem(value: 'B', child: Text('B')),
            DropdownMenuItem(value: 'C', child: Text('C')),
            DropdownMenuItem(value: 'D', child: Text('D')),
            DropdownMenuItem(value: 'E', child: Text('E')),
          ],
          onChanged: (v) => setState(() => _category = v ?? ''),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _diagnosis,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Diagnosis (optional)'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: Text('Drugs (${_lines.length})',
                style: TextStyle(
                    color: context.labelColor, fontWeight: FontWeight.w700)),
          ),
          TextButton.icon(
            onPressed: _addLine,
            icon: const Icon(Icons.add, size: 18),
            label: const Text('Add drug'),
          ),
        ]),
        for (var i = 0; i < _lines.length; i++)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: Text('${_lines[i].name} ×${_lines[i].quantity}',
                style: TextStyle(color: context.labelColor, fontSize: 14)),
            subtitle: Text(
              [
                if (_lines[i].dosage.isNotEmpty) _lines[i].dosage,
                if (_lines[i].duration.isNotEmpty) _lines[i].duration,
              ].join(' · '),
              style: TextStyle(color: context.hintColor, fontSize: 12),
            ),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline, size: 18),
              onPressed: () => setState(() => _lines.removeAt(i)),
            ),
          ),
      ],
    );
  }
}

/// Quantity and directions for one drug being written onto a script.
class _LineDialog extends StatefulWidget {
  final Map<String, dynamic> item;
  const _LineDialog({required this.item});

  @override
  State<_LineDialog> createState() => _LineDialogState();
}

class _LineDialogState extends State<_LineDialog> {
  final _qty = TextEditingController(text: '1');
  final _dosage = TextEditingController();
  final _duration = TextEditingController();
  final _instructions = TextEditingController();

  @override
  void dispose() {
    _qty.dispose();
    _dosage.dispose();
    _duration.dispose();
    _instructions.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('${widget.item['name']}'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: _qty,
            autofocus: true,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Quantity'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _dosage,
            decoration: const InputDecoration(
                labelText: 'Dosage', hintText: '1 tablet twice daily'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _duration,
            decoration: const InputDecoration(
                labelText: 'Duration', hintText: '5 days'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _instructions,
            decoration: const InputDecoration(labelText: 'Instructions'),
          ),
        ]),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            final qty = int.tryParse(_qty.text.trim()) ?? 0;
            if (qty < 1) {
              showError(context, 'A line needs at least one unit.');
              return;
            }
            Navigator.of(context).pop(RxLineDraft(
              name: '${widget.item['name']}',
              quantity: qty,
              itemId: widget.item['id'] as int?,
              dosage: _dosage.text,
              duration: _duration.text,
              instructions: _instructions.text,
            ));
          },
          child: const Text('Add'),
        ),
      ],
    );
  }
}
