import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Counter scripts — GET /api/prescriptions/scripts/.
///
/// The counter's script: who it is for, a list of drugs, and a line-by-
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
          path: '/api/prescriptions/scripts/',
          searchHint: 'Patient, phone, doctor or diagnosis…',
          fabLabel: 'Write up a script',
          showFab: isPharmacyStaff(role),
          emptyIcon: Icons.description_outlined,
          emptyTitle: 'No scripts yet',
          emptyMessage: 'Write up the paper script and dispense off it.',
          savedMessage: 'Prescription saved.',
          filters: const [
            ReportFilter(param: 'status', anyLabel: 'Any state', options: {
              // The API's alias for pending+partial: "still owed" is one
              // question at the counter, so it is one filter here too.
              'undispensed': 'Still owed',
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
    final prescriber = scriptWriter(row);
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
    final fresh = await api.get('/api/prescriptions/scripts/${_rx['id']}/');
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
      '/api/prescriptions/scripts/${_rx['id']}/$action/',
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
              'Rx${_rx['id']} · ${scriptWriter(_rx)}',
              style: TextStyle(color: context.hintColor, fontSize: 13)),
          if ('${_rx['diagnosis'] ?? ''}'.trim().isNotEmpty)
            Text('${_rx['diagnosis']}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
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

/// Write a script for one patient, off their own record rather than the
/// counter's list. The patient rides along on the script, so what the counter
/// dispenses off it lands in that patient's history instead of a name string.
Future<bool> writeScriptFor(
    BuildContext context, Map<String, dynamic> patient) async {
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _RxForm(patient: patient),
  );
  return saved == true;
}

/// Write up a paper script: who it is for, who wrote it, and the drugs on it.
class _RxForm extends StatefulWidget {
  /// Set when the script is being written from a patient's record — their
  /// name and phone fill the form and the script is filed against them.
  final Map<String, dynamic>? patient;
  const _RxForm({this.patient});

  @override
  State<_RxForm> createState() => _RxFormState();
}

class _RxFormState extends State<_RxForm> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _diagnosis = TextEditingController();
  final _doctor = TextEditingController();
  final _lines = <RxLineDraft>[];
  Map<String, dynamic>? _customer;
  late Map<String, dynamic>? _patient = widget.patient;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final p = widget.patient;
    if (p != null) {
      _name.text = '${p['full_name'] ?? ''}';
      _phone.text = '${p['phone'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _diagnosis.dispose();
    _doctor.dispose();
    super.dispose();
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
      _patient = null;
      _name.text = '${row['name']}';
      _phone.text = '${row['phone'] ?? ''}';
    });
  }

  /// The facility's patient register, so the script lands in their history.
  Future<void> _pickPatient() async {
    final row = await pickRow(
      context,
      path: '/api/patients/',
      title: 'Which patient?',
      hint: 'Name, hospital number or phone…',
      label: (r) => '${r['full_name']}',
      subtitle: (r) => '${r['hospital_number'] ?? ''} · ${r['phone'] ?? ''}',
    );
    if (row == null) return;
    setState(() {
      _patient = row;
      _customer = null;
      _name.text = '${row['full_name'] ?? ''}';
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
        '/api/prescriptions/scripts/',
        prescriptionBody(
          customerName: _name.text,
          customerPhone: _phone.text,
          lines: _lines,
          customerId: _customer?['id'] as int?,
          patientId: _patient?['id'] as int?,
          doctorName: _doctor.text,
          diagnosis: _diagnosis.text,
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
    final patient = widget.patient;
    return ReportFormSheet(
      title: patient == null
          ? 'Write up a script'
          : 'Prescribe for ${patient['full_name']}',
      saving: _saving,
      error: _error,
      submitLabel: 'Save script',
      onSubmit: _submit,
      children: [
        Row(children: [
          Expanded(
            child: TextField(
              controller: _name,
              decoration: InputDecoration(
                labelText: 'Patient name',
                hintText: 'Walk-in',
                helperText: _patient == null
                    ? null
                    : 'Filed against ${_patient!['hospital_number']}',
              ),
            ),
          ),
          // A counter customer or a registered patient puts a name on the
          // script; writing from a patient's record already carries one.
          if (patient == null) ...[
            TextButton(onPressed: _pickCustomer, child: const Text('Customer')),
            TextButton(onPressed: _pickPatient, child: const Text('Patient')),
          ],
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(labelText: 'Phone (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _doctor,
          decoration: const InputDecoration(
            labelText: 'Written by (optional)',
            helperText: 'Leave blank when you are prescribing it yourself',
          ),
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
