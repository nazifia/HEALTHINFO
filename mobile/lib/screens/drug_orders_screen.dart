import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/widgets/bar_chart.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Drug orders — GET/POST /api/prescriptions/.
///
/// What a clinician prescribed: one row per drug, with the dose, how often and
/// for how long. Not the counter's script (/api/prescriptions/scripts/) — that
/// is the pharmacy's paperwork for handing stock over. A doctor with no
/// pharmacy beside them still writes the order here, and the pharmacy marks it
/// dispensed when it fills it.
class DrugOrdersScreen extends StatelessWidget {
  const DrugOrdersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) => ReportListScreen(
        path: '/api/prescriptions/',
        fabLabel: 'Prescribe',
        showFab: api.roleCanReport(snap.data),
        emptyIcon: Icons.medication_outlined,
        emptyTitle: 'No drug orders yet',
        emptyMessage: 'Tap "Prescribe" to write the first one.',
        savedMessage: 'Order written.',
        filters: const [
          ReportFilter(param: 'status', anyLabel: 'Any state', options: {
            'prescribed': 'Prescribed',
            'partially_dispensed': 'Part-dispensed',
            'dispensed': 'Dispensed',
            'cancelled': 'Cancelled',
          }),
        ],
        header: (items) => _Header(items: items),
        card: (row, reload, edit) => _Card(row: row, edit: edit),
        form: (existing) => DrugOrderForm(existing: existing),
      ),
    );
  }
}

/// Write an order for one patient, straight off their record. Pops true when
/// something was saved. Pass [caseReport] when the order comes off a visit that
/// reached a diagnosis, so the order is filed against its reason.
Future<bool> prescribeFor(BuildContext context, Map<String, dynamic> patient,
    {int? caseReport}) async {
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => DrugOrderForm(patient: patient, caseReport: caseReport),
  );
  return saved == true;
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final out = items.where((r) => r['status'] == 'dispensed').length;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.medication_outlined,
          title: 'Drug orders',
          subtitle: '${items.length} order${items.length == 1 ? '' : 's'} written',
          color: EnhancedTheme.primaryTeal,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.edit_note_outlined,
              label: 'Written',
              value: '${items.length}',
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.check_circle_outline,
              label: 'Dispensed',
              value: '$out',
              color: EnhancedTheme.accentPurple),
          KpiTile(
              icon: Icons.pending_outlined,
              label: 'Waiting',
              value: '${items.length - out}',
              color: EnhancedTheme.accentOrange),
        ]),
        const SizedBox(height: 10),
        if (countBy(items, 'medication_name').isNotEmpty)
          StatSection(
            icon: Icons.bar_chart_rounded,
            heading: 'Orders by drug',
            child: MiniBarChart(rows: countBy(items, 'medication_name')),
          ),
      ]),
    );
  }
}

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback edit;
  const _Card({required this.row, required this.edit});

  @override
  Widget build(BuildContext context) {
    final directions = [
      '${row['dose'] ?? ''}',
      '${row['frequency'] ?? ''}',
      if (row['duration_days'] != null) 'for ${row['duration_days']} day(s)',
    ].where((v) => v.trim().isNotEmpty).join(' · ');
    final patient = '${row['patient_name'] ?? ''}'.trim();
    final reporter = '${row['reporter_name'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['medication_name'] ?? 'Drug'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}'.replaceAll('_', ' '),
              color: row['status'] == 'dispensed'
                  ? EnhancedTheme.successGreen
                  : EnhancedTheme.accentOrange),
          FutureBuilder<String?>(
            future: api.myRole(),
            builder: (context, snap) => api.roleCanReport(snap.data)
                ? IconButton(
                    visualDensity: VisualDensity.compact,
                    icon: Icon(Icons.edit_outlined,
                        size: 18, color: context.hintColor),
                    onPressed: edit)
                : const SizedBox.shrink(),
          ),
        ]),
        if (directions.isNotEmpty)
          Text(directions,
              style: TextStyle(color: context.labelColor, fontSize: 13)),
        const SizedBox(height: 4),
        Text(
          [
            // An order with no patient is the prescriber's working note — the
            // pharmacy never sees it, so say so rather than showing a blank.
            patient.isEmpty ? 'No patient linked' : patient,
            if (reporter.isNotEmpty) 'by $reporter',
          ].join('  ·  '),
          style: TextStyle(color: context.hintColor, fontSize: 11),
        ),
      ]),
    );
  }
}

/// One drug order: the patient, the drug, and the directions on it.
class DrugOrderForm extends StatefulWidget {
  final Map<String, dynamic>? existing;

  /// Set when prescribing from a patient's own record — the patient is fixed
  /// and the picker is not offered.
  final Map<String, dynamic>? patient;

  /// The case report this order treats, when it is written off a consultation
  /// that reached one. Null is still a valid order — it just carries no
  /// diagnosis to explain it.
  final int? caseReport;
  const DrugOrderForm(
      {super.key, this.existing, this.patient, this.caseReport});

  @override
  State<DrugOrderForm> createState() => _DrugOrderFormState();
}

class _DrugOrderFormState extends State<DrugOrderForm> {
  final _dose = TextEditingController();
  final _frequency = TextEditingController();
  final _duration = TextEditingController();
  final _notes = TextEditingController();
  Map<String, dynamic>? _medication;
  String? _medicationName;
  int? _patientId;
  String? _patientLabel;
  String _region = '';
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
      _medication = {'id': e['medication']};
      _medicationName = '${e['medication_name'] ?? ''}';
      _dose.text = '${e['dose'] ?? ''}';
      _frequency.text = '${e['frequency'] ?? ''}';
      _duration.text = '${e['duration_days'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
    }
    final p = widget.patient;
    if (p != null) {
      _patientId = p['id'] as int?;
      _patientLabel = '${p['full_name'] ?? ''} · ${p['hospital_number'] ?? ''}';
      _region = '${p['region'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _dose.dispose();
    _frequency.dispose();
    _duration.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickMedication() async {
    final row = await pickRow(
      context,
      path: '/api/medications/',
      title: 'Which drug?',
      hint: 'Generic or brand name…',
      label: (r) => '${r['generic_name']}',
      subtitle: (r) => [
        '${r['brand_name'] ?? ''}',
        '${r['drug_class'] ?? ''}',
      ].where((v) => v.trim().isNotEmpty).join(' · '),
    );
    if (row == null) return;
    setState(() {
      _medication = row;
      _medicationName = '${row['generic_name']}';
    });
  }

  Future<void> _submit() async {
    if (_medication == null) {
      setState(() => _error = 'Pick the drug being prescribed.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'patient': _patientId,
        'medication': _medication!['id'],
        'dose': _dose.text.trim(),
        'frequency': _frequency.text.trim(),
        // Blank means open-ended, which is null on the model, not zero days.
        'duration_days': int.tryParse(_duration.text.trim()),
        'region': _region,
        'notes': _notes.text.trim(),
        // Only when the caller knows it: sending null on an edit would strip
        // the case off an order that already has one.
        if (widget.caseReport != null) 'case_report': widget.caseReport,
      };
      if (_isEdit) {
        await api.patch('/api/prescriptions/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/prescriptions/', body);
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
      title: _isEdit ? 'Edit order' : 'Prescribe a drug',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Write order',
      onSubmit: _submit,
      children: [
        InputDecorator(
          decoration: InputDecoration(
            labelText: 'Drug',
            helperText: widget.patient == null
                ? null
                : 'For ${widget.patient!['full_name']}',
          ),
          child: Row(children: [
            Expanded(
              child: Text(_medicationName ?? 'Not picked',
                  style: TextStyle(
                      color: _medicationName == null
                          ? context.hintColor
                          : context.labelColor),
                  overflow: TextOverflow.ellipsis),
            ),
            TextButton(
                onPressed: _pickMedication,
                child: Text(_medicationName == null ? 'Pick' : 'Change')),
          ]),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _dose,
          decoration: const InputDecoration(
              labelText: 'Dose', hintText: '500 mg'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _frequency,
          decoration: const InputDecoration(
              labelText: 'Frequency', hintText: 'twice daily'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _duration,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
              labelText: 'Duration in days',
              helperText: 'Leave blank for an open-ended course'),
        ),
        const SizedBox(height: 12),
        // Prescribing off a patient's record fixes who it is for; the picker
        // is only for an order written from the list.
        if (widget.patient == null) ...[
          PatientPicker(
            initialId: _patientId,
            initialLabel: _patientLabel,
            onChanged: (id) => _patientId = id,
          ),
          const SizedBox(height: 12),
        ],
        RegionPicker(
            initial: _region.isEmpty ? null : _region,
            onChanged: (r) => _region = r),
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
