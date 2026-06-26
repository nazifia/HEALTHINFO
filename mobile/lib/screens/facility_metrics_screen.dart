import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'report_scaffold.dart';

/// Facility KPI snapshots — GET/POST /api/facility-metrics/.
/// Daily service-performance: bed occupancy, waiting time, staffing, throughput.
class FacilityMetricsScreen extends StatelessWidget {
  const FacilityMetricsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/facility-metrics/',
      fabLabel: 'Add snapshot',
      emptyIcon: Icons.local_hospital_outlined,
      emptyTitle: 'No facility metrics yet',
      emptyMessage: 'Tap "Add snapshot" to record today\'s KPIs.',
      savedMessage: 'Snapshot saved.',
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

/// KPI summary across all loaded snapshots: latest occupancy + sparkline,
/// total patients treated, average wait.
class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  num _n(Map<String, dynamic> r, String k) => (r[k] as num?) ?? 0;

  @override
  Widget build(BuildContext context) {
    // Rows arrive newest-first; reverse for a left→right (old→new) sparkline.
    final occ = [
      for (final r in items.reversed) (_n(r, 'occupancy_rate') * 100),
    ];
    final latestOcc = occ.isEmpty ? null : occ.last.round();
    final treated = items.fold<num>(0, (a, r) => a + _n(r, 'patients_treated'));
    final waits = [for (final r in items) _n(r, 'avg_wait_minutes')];
    final avgWait =
        waits.isEmpty ? 0 : (waits.reduce((a, b) => a + b) / waits.length).round();
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.local_hospital_outlined,
            title: 'Facility metrics',
            subtitle: '${items.length} snapshot${items.length == 1 ? '' : 's'}',
            color: EnhancedTheme.accentCyan,
          ),
          KpiRow(tiles: [
            KpiTile(
              icon: Icons.bed_outlined,
              label: 'Latest occupancy',
              value: latestOcc == null ? '—' : '$latestOcc%',
              color: EnhancedTheme.primaryTeal,
              spark: occ.length > 1 ? occ : null,
            ),
            KpiTile(
              icon: Icons.healing_outlined,
              label: 'Patients treated',
              value: '$treated',
              color: EnhancedTheme.accentPurple,
            ),
            KpiTile(
              icon: Icons.timer_outlined,
              label: 'Avg wait (min)',
              value: '$avgWait',
              color: EnhancedTheme.accentOrange,
            ),
            KpiTile(
              icon: Icons.group_outlined,
              label: 'Latest staff',
              value: items.isEmpty ? '—' : '${_n(items.first, 'staff_on_duty')}',
              color: EnhancedTheme.infoBlue,
            ),
          ]),
          const SizedBox(height: 10),
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
    final rate = row['occupancy_rate'];
    final occ = rate is num ? '${(rate * 100).toStringAsFixed(0)}%' : '—';
    final wait = row['avg_wait_minutes'] ?? 0;
    final staff = row['staff_on_duty'] ?? 0;
    final treated = row['patients_treated'] ?? 0;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text('$treated patients treated',
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(text: 'occ $occ', color: EnhancedTheme.primaryTeal),
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
          Text('Beds ${row['beds_occupied'] ?? 0}/${row['beds_total'] ?? 0}  ·  '
              'wait ${wait}m  ·  staff $staff',
              style: TextStyle(color: context.subLabelColor, fontSize: 13)),
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/facility-metrics/${row['id']}/',
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
  final _bedsTotal = TextEditingController(text: '0');
  final _bedsOccupied = TextEditingController(text: '0');
  final _wait = TextEditingController(text: '0');
  final _staff = TextEditingController(text: '0');
  final _treated = TextEditingController(text: '0');
  final _notes = TextEditingController();
  String _region = '';
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _bedsTotal.text = '${e['beds_total'] ?? 0}';
      _bedsOccupied.text = '${e['beds_occupied'] ?? 0}';
      _wait.text = '${e['avg_wait_minutes'] ?? 0}';
      _staff.text = '${e['staff_on_duty'] ?? 0}';
      _treated.text = '${e['patients_treated'] ?? 0}';
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _bedsTotal.dispose();
    _bedsOccupied.dispose();
    _wait.dispose();
    _staff.dispose();
    _treated.dispose();
    _notes.dispose();
    super.dispose();
  }

  int _n(TextEditingController c) => int.tryParse(c.text.trim()) ?? 0;

  Future<void> _submit() async {
    if (_n(_bedsOccupied) > _n(_bedsTotal)) {
      setState(() => _error = 'Occupied beds cannot exceed total beds.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'beds_total': _n(_bedsTotal),
        'beds_occupied': _n(_bedsOccupied),
        'avg_wait_minutes': _n(_wait),
        'staff_on_duty': _n(_staff),
        'patients_treated': _n(_treated),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/facility-metrics/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/facility-metrics/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _numField(TextEditingController c, String label) => TextField(
        controller: c,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(labelText: label),
      );

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _isEdit ? 'Edit metrics' : 'Add facility metrics',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit snapshot',
      onSubmit: _submit,
      children: [
        Row(children: [
          Expanded(child: _numField(_bedsTotal, 'Beds total')),
          const SizedBox(width: 12),
          Expanded(child: _numField(_bedsOccupied, 'Beds occupied')),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _numField(_wait, 'Avg wait (min)')),
          const SizedBox(width: 12),
          Expanded(child: _numField(_staff, 'Staff on duty')),
        ]),
        const SizedBox(height: 12),
        _numField(_treated, 'Patients treated'),
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
