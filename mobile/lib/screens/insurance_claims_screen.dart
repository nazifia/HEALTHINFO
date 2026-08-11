import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/widgets/bar_chart.dart';
import 'report_scaffold.dart';

/// Health-insurance claims — GET/POST /api/insurance-claims/.
/// Utilization + cost signal; diagnosis links to the catalog for ICD-10 pooling.
class InsuranceClaimsScreen extends StatelessWidget {
  const InsuranceClaimsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/insurance-claims/',
      fabLabel: 'Add claim',
      emptyIcon: Icons.receipt_long_outlined,
      emptyTitle: 'No claims yet',
      emptyMessage: 'Tap "Add claim" to file the first one.',
      savedMessage: 'Claim saved.',
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

/// Chart summary: totals + approval-rate donut + status & diagnosis breakdowns.
class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final approved =
        countEq(items, 'status', 'approved') + countEq(items, 'status', 'paid');
    final totalAmount = items.fold<num>(
        0, (a, r) => a + ((r['amount'] as num?) ?? 0));
    final byStatus = countBy(items, 'status');
    final byDx = countBy(items, 'diagnosis_name');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.receipt_long_outlined,
            title: 'Insurance claims',
            subtitle: '${items.length} claim${items.length == 1 ? '' : 's'}',
            color: EnhancedTheme.infoBlue,
          ),
          KpiRow(tiles: [
            KpiTile(
                icon: Icons.receipt_long_outlined,
                label: 'Claims',
                value: '${items.length}',
                color: EnhancedTheme.infoBlue),
            KpiTile(
                icon: Icons.payments_outlined,
                label: 'Total (₦)',
                value: '$totalAmount',
                color: EnhancedTheme.successGreen),
            KpiTile(
                icon: Icons.verified_outlined,
                label: 'Approved',
                value: '$approved',
                color: EnhancedTheme.primaryTeal),
          ]),
          const SizedBox(height: 10),
          if (items.isNotEmpty)
            StatSection(
              icon: Icons.verified_outlined,
              heading: 'Approval rate',
              child: Center(
                child: DonutChart(
                  value: approved,
                  total: items.length,
                  centerLabel: pctOf(approved / items.length),
                  centerSub: 'approved',
                ),
              ),
            ),
          if (byStatus.isNotEmpty)
            StatSection(
              icon: Icons.bar_chart_rounded,
              heading: 'By status',
              child: MiniBarChart(rows: byStatus),
            ),
          if (byDx.isNotEmpty)
            StatSection(
              icon: Icons.coronavirus_outlined,
              heading: 'Top diagnoses',
              color: EnhancedTheme.accentOrange,
              child: MiniBarChart(rows: byDx),
            ),
        ],
      ),
    );
  }
}

const _statuses = ['submitted', 'approved', 'rejected', 'paid'];

const _statusColor = {
  'submitted': EnhancedTheme.infoBlue,
  'approved': EnhancedTheme.successGreen,
  'rejected': EnhancedTheme.errorRed,
  'paid': EnhancedTheme.primaryTeal,
};

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final VoidCallback edit;
  const _Card({required this.row, required this.reload, required this.edit});

  @override
  Widget build(BuildContext context) {
    final status = '${row['status'] ?? ''}';
    final amount = '${row['amount'] ?? ''}'.trim();
    final dx = '${row['diagnosis_name'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(amount.isEmpty ? 'Claim #${row['id']}' : '₦$amount',
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(text: status, color: _statusColor[status] ?? EnhancedTheme.primaryTeal),
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
          if (dx.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(dx, style: TextStyle(color: context.subLabelColor, fontSize: 13)),
          ],
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/insurance-claims/${row['id']}/',
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
  final _amount = TextEditingController(text: '0');
  final _age = TextEditingController();
  final _notes = TextEditingController();
  String _status = 'submitted';
  String _region = '';
  int? _diagnosisId;
  List<Map<String, dynamic>> _diseases = [];
  int? _patientId;
  String? _patientLabel;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _patientId = e['patient'] as int?;
      _patientLabel = '${e['patient_name'] ?? ''}';
      _amount.text = '${e['amount'] ?? 0}';
      _age.text = '${e['patient_age_group'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      if (_statuses.contains(e['status'])) _status = e['status'];
      _region = '${e['region'] ?? ''}';
      _diagnosisId = e['diagnosis'] as int?;
    }
    _loadDiseases();
  }

  Future<void> _loadDiseases() async {
    try {
      final rows = await api.getList('/api/diseases/');
      setState(() => _diseases = rows.cast<Map<String, dynamic>>());
    } catch (_) {}
  }

  @override
  void dispose() {
    _amount.dispose();
    _age.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'patient': _patientId,
        'diagnosis': _diagnosisId,
        'amount': double.tryParse(_amount.text.trim()) ?? 0,
        'status': _status,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/insurance-claims/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/insurance-claims/', body);
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
      title: _isEdit ? 'Edit claim' : 'New claim',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit claim',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Amount (₦)'),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _status,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Status'),
          items: [for (final s in _statuses) DropdownMenuItem(value: s, child: Text(s))],
          onChanged: (v) => setState(() => _status = v!),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int?>(
          initialValue: _diagnosisId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Diagnosis (optional)'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— none —')),
            for (final d in _diseases)
              DropdownMenuItem(value: d['id'] as int, child: Text('${d['name']}')),
          ],
          onChanged: (v) => setState(() => _diagnosisId = v),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _age,
          decoration: const InputDecoration(labelText: 'Patient age group'),
        ),
        const SizedBox(height: 12),
        PatientPicker(
          initialId: _patientId,
          initialLabel: _patientLabel,
          onChanged: (id) => _patientId = id,
        ),
        const SizedBox(height: 12),
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
