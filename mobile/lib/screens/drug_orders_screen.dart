import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
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
        collapse: collapseByGroup,
        card: (row, reload, edit) => _Card(row: row, reload: reload),
        form: (existing) => DrugOrderForm(existing: existing),
      ),
    );
  }
}

/// One card per prescription, not per drug: the drugs written together were
/// one decision, and listed apart a three-drug course reads as three
/// prescriptions. The kept row carries the whole prescription under `drugs`;
/// an order on no prescription — written before groups, or captured off a
/// counter script — stands on its own.
///
/// ponytail: folds the page it is handed, so a prescription split across two
/// pages shows on both. Group server-side the day that happens routinely.
List<Map<String, dynamic>> collapseByGroup(List<Map<String, dynamic>> rows) {
  final heads = <String, Map<String, dynamic>>{};
  final out = <Map<String, dynamic>>[];
  for (final row in rows) {
    final group = '${row['group'] ?? ''}';
    final head = group.isEmpty ? null : heads[group];
    if (head == null) {
      final kept = {...row, 'drugs': [row]};
      if (group.isNotEmpty) heads[group] = kept;
      out.add(kept);
    } else {
      (head['drugs'] as List).add(row);
    }
  }
  return out;
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

class _Card extends StatefulWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  const _Card({required this.row, required this.reload});

  @override
  State<_Card> createState() => _CardState();
}

class _CardState extends State<_Card> {
  Map<String, dynamic> get row => widget.row;

  /// The drugs of this prescription. A row that was never collapsed — an order
  /// on no prescription — is a prescription of one.
  List<Map<String, dynamic>> get _drugs =>
      ((row['drugs'] ?? [row]) as List).cast<Map<String, dynamic>>();

  static String _directions(Map<String, dynamic> drug) => [
        '${drug['dose'] ?? ''}',
        '${drug['frequency'] ?? ''}',
        if (drug['duration_days'] != null) 'for ${drug['duration_days']} day(s)',
      ].where((v) => v.trim().isNotEmpty).join(' · ');

  static bool _stoppable(Map<String, dynamic> drug) =>
      drug['status'] == 'prescribed' || drug['status'] == 'partially_dispensed';

  /// Edit one drug of the prescription. The sheet edits that drug alone: the
  /// others are their own orders and the pharmacy dispenses them separately.
  Future<void> _edit(Map<String, dynamic> drug) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => DrugOrderForm(existing: drug),
    );
    if (saved == true) widget.reload();
  }

  /// Stop the whole prescription, once it is confirmed.
  ///
  /// The confirmation says how many drugs stop, because the rest of the course
  /// goes with the one on screen and nobody should find that out afterwards.
  Future<void> _cancel() async {
    final drugs = _drugs;
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel this prescription?'),
        content: Text(drugs.length == 1
            ? 'The order for ${drugs.first['medication_name']} stops.'
            : 'All ${drugs.length} drugs on it stop. Anything already '
                'dispensed stays dispensed.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Keep it')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Cancel prescription')),
        ],
      ),
    );
    if (go != true || !mounted) return;
    try {
      final r = await api.post('/api/prescriptions/${row['id']}/cancel/');
      if (!mounted) return;
      showSuccess(context, '${r?['message'] ?? 'Cancelled.'}');
      widget.reload();
    } catch (e) {
      if (mounted) showError(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final drugs = _drugs;
    // Drugs of one prescription reach the counter separately, so they are not
    // always at the same stage; the badge says that rather than picking one.
    final states = drugs.map((d) => '${d['status']}').toSet();
    final state = states.length == 1 ? states.first : 'part dispensed';
    final patient = '${row['patient_name'] ?? ''}'.trim();
    final reporter = '${row['reporter_name'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
                drugs.length == 1
                    ? '${drugs.first['medication_name'] ?? 'Drug'}'
                    : '${drugs.length} drugs',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: state.replaceAll('_', ' '),
              color: state == 'dispensed'
                  ? EnhancedTheme.successGreen
                  : EnhancedTheme.accentOrange),
          FutureBuilder<String?>(
            future: api.myRole(),
            builder: (context, snap) {
              if (!api.roleCanReport(snap.data)) return const SizedBox.shrink();
              // Nothing to stop once every drug is dispensed or cancelled.
              if (!drugs.any(_stoppable)) return const SizedBox.shrink();
              return IconButton(
                  visualDensity: VisualDensity.compact,
                  tooltip: 'Cancel prescription',
                  icon: Icon(Icons.block_outlined,
                      size: 18, color: EnhancedTheme.errorRed),
                  onPressed: _cancel);
            },
          ),
        ]),
        for (final drug in drugs)
          Row(children: [
            Expanded(
              child: Text(
                  [
                    if (drugs.length > 1) '${drug['medication_name'] ?? 'Drug'}',
                    _directions(drug),
                  ].where((v) => v.trim().isNotEmpty).join(' — '),
                  style: TextStyle(color: context.labelColor, fontSize: 13)),
            ),
            FutureBuilder<String?>(
              future: api.myRole(),
              builder: (context, snap) => api.roleCanReport(snap.data)
                  ? IconButton(
                      visualDensity: VisualDensity.compact,
                      icon: Icon(Icons.edit_outlined,
                          size: 18, color: context.hintColor),
                      onPressed: () => _edit(drug))
                  : const SizedBox.shrink(),
            ),
          ]),
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

/// One prescription for one patient: the drugs on it and the directions.
///
/// A visit rarely calls for a single drug, so drugs are stacked up and written
/// together. Each becomes its own order row — the pharmacy dispenses them one
/// at a time — but the patient is prescribed for once.
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

/// A drug stacked onto the prescription being written.
class _DrugDraft {
  final int medication;
  final String name;
  final String dose;
  final String frequency;
  final int? durationDays;

  const _DrugDraft({
    required this.medication,
    required this.name,
    required this.dose,
    required this.frequency,
    this.durationDays,
  });

  Map<String, dynamic> get body => {
        'medication': medication,
        'dose': dose,
        'frequency': frequency,
        // Blank means open-ended, which is null on the model, not zero days.
        'duration_days': durationDays,
      };

  String get directions => [
        dose,
        frequency,
        if (durationDays != null) 'for $durationDays day(s)',
      ].where((v) => v.trim().isNotEmpty).join(' · ');
}

class _DrugOrderFormState extends State<DrugOrderForm> {
  final _drugs = <_DrugDraft>[];
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

  /// The drug in the fields right now, or null when none is picked.
  _DrugDraft? _pending() {
    final med = _medication;
    if (med == null) return null;
    return _DrugDraft(
      medication: med['id'] as int,
      name: _medicationName ?? '',
      dose: _dose.text.trim(),
      frequency: _frequency.text.trim(),
      durationDays: int.tryParse(_duration.text.trim()),
    );
  }

  /// Stack the drug in the fields and clear them for the next one.
  void _addAnother() {
    final drug = _pending();
    if (drug == null) {
      setState(() => _error = 'Pick the drug being prescribed.');
      return;
    }
    setState(() {
      _drugs.add(drug);
      _medication = null;
      _medicationName = null;
      _dose.clear();
      _frequency.clear();
      _duration.clear();
      _error = null;
    });
  }

  Future<void> _submit() async {
    // The drug still in the fields counts: nobody should have to press "Add
    // another drug" to write the only one they wanted.
    final drugs = [..._drugs, if (_pending() != null) _pending()!];
    if (drugs.isEmpty) {
      setState(() => _error = 'Pick the drug being prescribed.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final shared = {
        'patient': _patientId,
        'region': _region,
        'notes': _notes.text.trim(),
        // Only when the caller knows it: sending null on an edit would strip
        // the case off an order that already has one.
        if (widget.caseReport != null) 'case_report': widget.caseReport,
      };
      if (_isEdit) {
        await api.patch('/api/prescriptions/${widget.existing!['id']}/',
            {...shared, ...drugs.first.body});
      } else {
        // A list is one prescription of several drugs, written whole or
        // not at all — see PrescriptionViewSet.get_serializer.
        await api.post('/api/prescriptions/',
            [for (final drug in drugs) {...shared, ...drug.body}]);
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
    final written = _drugs.length + (_pending() == null ? 0 : 1);
    return ReportFormSheet(
      title: _isEdit ? 'Edit order' : 'Prescribe',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit
          ? 'Save changes'
          : 'Write order${written == 1 ? '' : 's'}',
      onSubmit: _submit,
      children: [
        for (var i = 0; i < _drugs.length; i++)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.medication_outlined, size: 18),
            title: Text(_drugs[i].name,
                style: TextStyle(color: context.labelColor, fontSize: 14)),
            subtitle: _drugs[i].directions.isEmpty
                ? null
                : Text(_drugs[i].directions,
                    style: TextStyle(color: context.hintColor, fontSize: 12)),
            trailing: IconButton(
              icon: Icon(Icons.close, size: 18, color: context.hintColor),
              onPressed: () => setState(() => _drugs.removeAt(i)),
            ),
          ),
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
        // An order is edited one drug at a time: the row on screen is that
        // drug, and stacking more onto it would rewrite a different order.
        if (!_isEdit)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: _addAnother,
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Add another drug'),
            ),
          ),
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
