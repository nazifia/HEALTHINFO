import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/searchable_dropdown.dart';
import 'report_scaffold.dart';

/// Pharmacy stock & usage — GET/POST /api/stock-reports/.
/// One snapshot per medication: units on hand, units consumed, and a shortage
/// flag so central can spot and resupply stock-outs.
class StockReportsScreen extends StatelessWidget {
  const StockReportsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/stock-reports/',
      fabLabel: 'Add snapshot',
      emptyIcon: Icons.inventory_2_outlined,
      emptyTitle: 'No stock reports yet',
      emptyMessage: 'Tap "Add snapshot" to record stock levels.',
      savedMessage: 'Snapshot saved.',
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

/// Chart summary: totals + shortage share donut + most-consumed medications.
class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final shortages = countTrue(items, 'shortage');
    // Sum consumed units per medication, biggest 6.
    final consumed = <String, num>{};
    for (final r in items) {
      final med = '${r['medication_name'] ?? ''}'.trim();
      if (med.isEmpty) continue;
      consumed[med] = (consumed[med] ?? 0) + ((r['consumed'] as num?) ?? 0);
    }
    final topConsumed = consumed.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final totalConsumed = consumed.values.fold<num>(0, (a, b) => a + b);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.inventory_2_outlined,
            title: 'Pharmacy stock',
            subtitle: '${items.length} snapshot${items.length == 1 ? '' : 's'}',
            color: EnhancedTheme.accentOrange,
          ),
          KpiRow(tiles: [
            KpiTile(
                icon: Icons.medication_outlined,
                label: 'Medications',
                value: '${distinctCount(items, 'medication_name')}',
                color: EnhancedTheme.primaryTeal),
            KpiTile(
                icon: Icons.warning_amber_rounded,
                label: 'Shortages',
                value: '$shortages',
                color: EnhancedTheme.errorRed),
            KpiTile(
                icon: Icons.local_pharmacy_outlined,
                label: 'Units consumed',
                value: '$totalConsumed',
                color: EnhancedTheme.accentOrange),
          ]),
          const SizedBox(height: 10),
          if (items.isNotEmpty)
            StatSection(
              icon: Icons.warning_amber_rounded,
              heading: 'Shortage share',
              color: EnhancedTheme.errorRed,
              child: Center(
                child: DonutChart(
                  value: shortages,
                  total: items.length,
                  color: EnhancedTheme.errorRed,
                  centerLabel: '$shortages',
                  centerSub: 'in shortage',
                ),
              ),
            ),
          if (topConsumed.isNotEmpty)
            StatSection(
              icon: Icons.bar_chart_rounded,
              heading: 'Most consumed',
              color: EnhancedTheme.accentOrange,
              child: MiniBarChart(rows: [
                for (final e in topConsumed.take(6)) (label: e.key, value: e.value),
              ]),
            ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final VoidCallback edit;
  const _Card({required this.row, required this.reload, required this.edit});

  @override
  Widget build(BuildContext context) {
    final med = '${row['medication_name'] ?? ''}'.trim();
    final onHand = row['on_hand'] ?? 0;
    final consumed = row['consumed'] ?? 0;
    final shortage = row['shortage'] == true;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(med.isEmpty ? 'Stock #${row['id']}' : med,
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            if (shortage)
              const ReportBadge(text: 'shortage', color: EnhancedTheme.errorRed),
            FutureBuilder<String?>(
              future: api.myRole(),
              builder: (context, snap) => api.roleCanReport(snap.data)
                  ? IconButton(
                      visualDensity: VisualDensity.compact,
                      icon: Icon(Icons.edit_outlined, size: 18, color: context.hintColor),
                      onPressed: edit)
                  : const SizedBox.shrink(),
            ),
          ]),
          const SizedBox(height: 6),
          Text('On hand $onHand  ·  consumed $consumed',
              style: TextStyle(color: context.subLabelColor, fontSize: 13)),
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/stock-reports/${row['id']}/',
            current: '${row['region'] ?? ''}'.trim(),
            onSaved: reload,
          ),
        ],
      ),
    );
  }
}

class _Form extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _Form({this.existing});

  @override
  State<_Form> createState() => _FormState();
}

class _FormState extends State<_Form> {
  final _onHand = TextEditingController(text: '0');
  final _consumed = TextEditingController(text: '0');
  final _notes = TextEditingController();
  bool _shortage = false;
  String _region = '';
  int? _medicationId;
  List<Map<String, dynamic>> _medications = [];
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _onHand.text = '${e['on_hand'] ?? 0}';
      _consumed.text = '${e['consumed'] ?? 0}';
      _shortage = e['shortage'] == true;
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
      _medicationId = e['medication'] as int?;
    }
    _loadMeds();
  }

  Future<void> _loadMeds() async {
    try {
      final rows = await api.getList('/api/medications/');
      setState(() => _medications = rows.cast<Map<String, dynamic>>());
    } catch (_) {}
  }

  @override
  void dispose() {
    _onHand.dispose();
    _consumed.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_medicationId == null) {
      setState(() => _error = 'Pick a medication.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'medication': _medicationId,
        'on_hand': int.tryParse(_onHand.text.trim()) ?? 0,
        'consumed': int.tryParse(_consumed.text.trim()) ?? 0,
        'shortage': _shortage,
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/stock-reports/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/stock-reports/', body);
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
      title: _isEdit ? 'Edit stock snapshot' : 'Add stock snapshot',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit snapshot',
      onSubmit: _submit,
      children: [
        SearchableDropdown<int?>(
          initialValue: _medicationId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Medication'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— select —')),
            for (final m in _medications)
              DropdownMenuItem(value: m['id'] as int, child: Text('${m['generic_name']}')),
          ],
          onChanged: (v) => setState(() => _medicationId = v),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _onHand,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'On hand'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _consumed,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Consumed'),
            ),
          ),
        ]),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Shortage'),
          subtitle: const Text('Stocked out or below buffer'),
          value: _shortage,
          onChanged: (v) => setState(() => _shortage = v),
        ),
        RegionPicker(
            initial: _region.isEmpty ? null : _region, onChanged: (r) => _region = r),
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Notes'),
        ),
      ],
    );
  }
}
