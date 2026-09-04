import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';
import 'report_scaffold.dart';

const _dispositions = {
  'home': 'Discharged home',
  'follow_up': 'Discharged, follow-up',
  'admitted': 'Admitted',
  'referred': 'Referred out',
  'deceased': 'Died',
};

const _severities = ['mild', 'moderate', 'severe', 'critical'];

const _dispositionColor = {
  'home': EnhancedTheme.successGreen,
  'follow_up': EnhancedTheme.infoBlue,
  'admitted': EnhancedTheme.accentPurple,
  'referred': EnhancedTheme.accentCyan,
  'deceased': EnhancedTheme.errorRed,
};

/// Vital field name as the API sends it -> what a clinician calls it. The
/// abnormal-vitals list names fields, not labels.
const _vitalLabel = {
  'temperature_c': 'temp',
  'pulse_bpm': 'pulse',
  'respiratory_rate': 'resp rate',
  'systolic_bp': 'systolic',
  'diastolic_bp': 'diastolic',
  'oxygen_saturation': 'SpO2',
  'weight_kg': 'weight',
  'height_cm': 'height',
};

/// A date as the API wants it, or null when unset.
String? consultationDate(DateTime? d) => d == null
    ? null
    : '${d.year}-${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';

/// Consultations — GET/POST /api/consultations/.
/// The encounter itself: why the patient came, the triage vitals, and where
/// they went next. The diagnosis stays on the case report this links to, so
/// closing a consultation carries its disposition through to that case.
class ConsultationsScreen extends StatelessWidget {
  const ConsultationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/consultations/',
      fabLabel: 'New consultation',
      emptyIcon: Icons.medical_information_outlined,
      emptyTitle: 'No consultations yet',
      emptyMessage: 'Tap "New consultation" to start one.',
      savedMessage: 'Consultation saved.',
      filters: const [
        ReportFilter(param: 'status', anyLabel: 'Any status', options: {
          'open': 'Open',
          'closed': 'Closed',
        }),
        ReportFilter(
            param: 'disposition',
            anyLabel: 'Any disposition',
            options: _dispositions),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final open = countEq(items, 'status', 'open');
    final admitted = countEq(items, 'disposition', 'admitted');
    final closed = items.length - open;
    final byDisposition = countBy(items, 'disposition');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.medical_information_outlined,
            title: 'Consultations',
            subtitle: '${items.length} encounter${items.length == 1 ? '' : 's'}',
            color: EnhancedTheme.primaryTeal,
          ),
          KpiRow(tiles: [
            KpiTile(
                icon: Icons.medical_information_outlined,
                label: 'Total',
                value: '${items.length}',
                color: EnhancedTheme.primaryTeal),
            KpiTile(
                icon: Icons.pending_actions_outlined,
                label: 'Open',
                value: '$open',
                color: EnhancedTheme.infoBlue),
            KpiTile(
                icon: Icons.local_hospital_outlined,
                label: 'Admitted',
                value: '$admitted',
                color: EnhancedTheme.accentPurple),
          ]),
          const SizedBox(height: 10),
          if (closed > 0)
            StatSection(
              icon: Icons.local_hospital_outlined,
              heading: 'Admission rate',
              color: EnhancedTheme.accentPurple,
              child: Center(
                child: DonutChart(
                  value: admitted,
                  total: closed,
                  color: EnhancedTheme.accentPurple,
                  centerLabel: pctOf(admitted / closed),
                  centerSub: 'admitted',
                ),
              ),
            ),
          if (byDisposition.isNotEmpty)
            StatSection(
              icon: Icons.bar_chart_rounded,
              heading: 'By disposition',
              child: MiniBarChart(rows: byDisposition),
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
    final isOpen = '${row['status']}' == 'open';
    final disposition = '${row['disposition'] ?? ''}';
    final complaint = '${row['chief_complaint'] ?? ''}'.trim();
    final patient = '${row['patient_name'] ?? ''}'.trim();
    final bp = '${row['blood_pressure'] ?? ''}'.trim();
    // The diagnosis lives on the linked case report; the API sends its name.
    final diagnosis = '${row['case_report_disease'] ?? ''}'.trim();
    final abnormal =
        (row['abnormal_vitals'] as List?)?.cast<String>() ?? const <String>[];
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(
                complaint.isEmpty ? 'Consultation #${row['id']}' : complaint,
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15),
              ),
            ),
            const SizedBox(width: 8),
            ReportBadge(
                text: isOpen ? 'open' : 'closed',
                color:
                    isOpen ? EnhancedTheme.infoBlue : EnhancedTheme.successGreen),
            if (disposition.isNotEmpty) ...[
              const SizedBox(width: 6),
              ReportBadge(
                  text: disposition,
                  color:
                      _dispositionColor[disposition] ?? EnhancedTheme.primaryTeal),
            ],
            // A closed consultation is a signed note and the API refuses an
            // edit, so the pencil only shows while it is open.
            if (isOpen)
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
          if (patient.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(patient,
                style: TextStyle(color: context.hintColor, fontSize: 12)),
          ],
          if (diagnosis.isNotEmpty) ...[
            const SizedBox(height: 6),
            Row(children: [
              const Icon(Icons.assignment_outlined,
                  size: 14, color: EnhancedTheme.accentPurple),
              const SizedBox(width: 6),
              Expanded(
                child: Text('Dx: $diagnosis',
                    style: TextStyle(
                        color: context.labelColor,
                        fontSize: 13,
                        fontWeight: FontWeight.w600)),
              ),
            ]),
          ],
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: [
            if (row['temperature_c'] != null)
              _Vital(label: 'Temp', value: '${row['temperature_c']} C'),
            if (row['pulse_bpm'] != null)
              _Vital(label: 'Pulse', value: '${row['pulse_bpm']}'),
            if (bp.isNotEmpty) _Vital(label: 'BP', value: bp),
            if (row['oxygen_saturation'] != null)
              _Vital(label: 'SpO2', value: '${row['oxygen_saturation']}%'),
            if (row['bmi'] != null) _Vital(label: 'BMI', value: '${row['bmi']}'),
          ]),
          if (abnormal.isNotEmpty) ...[
            const SizedBox(height: 8),
            Row(children: [
              const Icon(Icons.warning_amber_rounded,
                  size: 16, color: EnhancedTheme.errorRed),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Outside triage band: '
                  '${abnormal.map((v) => _vitalLabel[v] ?? v).join(', ')}',
                  style: const TextStyle(
                      color: EnhancedTheme.errorRed, fontSize: 12),
                ),
              ),
            ]),
          ],
          if ('${row['follow_up_on'] ?? ''}'.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text('Follow-up ${row['follow_up_on']}',
                style: TextStyle(color: context.hintColor, fontSize: 12)),
          ],
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: RegionEditChip(
                path: '/api/consultations/${row['id']}/',
                current: '${row['region'] ?? ''}'.trim(),
                onSaved: reload,
              ),
            ),
            if (isOpen)
              FutureBuilder<String?>(
                future: api.myRole(),
                builder: (context, snap) => api.roleCanReport(snap.data)
                    ? TextButton.icon(
                        icon: const Icon(Icons.task_alt, size: 18),
                        label: const Text('Close'),
                        onPressed: () => _close(context),
                      )
                    : const SizedBox.shrink(),
              ),
          ]),
        ],
      ),
    );
  }

  Future<void> _close(BuildContext context) async {
    final done = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _CloseSheet(row: row),
    );
    if (done == true) {
      reload();
      if (context.mounted) showSuccess(context, 'Consultation closed.');
    }
  }
}

/// One triage reading as a compact chip.
class _Vital extends StatelessWidget {
  final String label;
  final String value;
  const _Vital({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: EnhancedTheme.primaryTeal.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text('$label $value',
          style: TextStyle(color: context.labelColor, fontSize: 12)),
    );
  }
}

/// Ends the encounter — POST /api/consultations/{id}/close/. Separate from the
/// edit form because closing also settles the booking and the case report, and
/// the API only does that through this action.
class _CloseSheet extends StatefulWidget {
  final Map<String, dynamic> row;
  const _CloseSheet({required this.row});

  @override
  State<_CloseSheet> createState() => _CloseSheetState();
}

class _CloseSheetState extends State<_CloseSheet> {
  String _disposition = 'home';
  DateTime? _followUp;
  final _notes = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickFollowUp() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _followUp ?? now.add(const Duration(days: 7)),
      firstDate: now,
      lastDate: DateTime(now.year + 2),
    );
    if (picked != null) setState(() => _followUp = picked);
  }

  Future<void> _submit() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post('/api/consultations/${widget.row['id']}/close/', {
        'disposition': _disposition,
        'follow_up_on': consultationDate(_followUp),
        'notes': _notes.text.trim(),
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
      title: 'Close consultation',
      saving: _saving,
      error: _error,
      submitLabel: 'Close consultation',
      onSubmit: _submit,
      children: [
        SearchableDropdown<String>(
          initialValue: _disposition,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Disposition'),
          items: [
            for (final d in _dispositions.entries)
              DropdownMenuItem(value: d.key, child: Text(d.value)),
          ],
          onChanged: (v) => setState(() => _disposition = v!),
        ),
        const SizedBox(height: 12),
        // Required for a follow-up disposition, optional otherwise — say which
        // before the round trip that would reject it.
        InputDecorator(
          decoration: InputDecoration(
            labelText: 'Follow-up date',
            helperText: _disposition == 'follow_up'
                ? 'Required for a follow-up disposition'
                : null,
          ),
          child: Row(children: [
            Expanded(
              child: Text(consultationDate(_followUp) ?? 'Not set',
                  style: TextStyle(
                      color: _followUp == null
                          ? context.hintColor
                          : context.labelColor)),
            ),
            if (_followUp != null)
              IconButton(
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.clear, size: 18),
                onPressed: () => setState(() => _followUp = null),
              ),
            TextButton(onPressed: _pickFollowUp, child: const Text('Pick')),
          ]),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Closing notes'),
        ),
      ],
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
  final _complaint = TextEditingController();
  final _temp = TextEditingController();
  final _pulse = TextEditingController();
  final _resp = TextEditingController();
  final _systolic = TextEditingController();
  final _diastolic = TextEditingController();
  final _spo2 = TextEditingController();
  final _weight = TextEditingController();
  final _height = TextEditingController();
  final _notes = TextEditingController();
  String _region = '';
  int? _patientId;
  String? _patientLabel;
  int? _caseReportId;
  int? _appointmentId;
  // The diagnosis. It is stored on the case report, not on the consultation —
  // the visit links to the case, so filling this in files or updates one.
  int? _diseaseId;
  String _severity = 'mild';
  List<Map<String, dynamic>> _diseases = const [];
  // The linked patient's existing cases, so this visit can be added to one
  // rather than filing a second case for the same illness.
  List<Map<String, dynamic>> _cases = const [];
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  static const _vitalFields = {
    'temperature_c': 'Temp C',
    'pulse_bpm': 'Pulse',
    'systolic_bp': 'Systolic',
    'diastolic_bp': 'Diastolic',
    'respiratory_rate': 'Resp rate',
    'oxygen_saturation': 'SpO2 %',
    'weight_kg': 'Weight kg',
    'height_cm': 'Height cm',
  };

  Map<String, TextEditingController> get _vitals => {
        'temperature_c': _temp,
        'pulse_bpm': _pulse,
        'systolic_bp': _systolic,
        'diastolic_bp': _diastolic,
        'respiratory_rate': _resp,
        'oxygen_saturation': _spo2,
        'weight_kg': _weight,
        'height_cm': _height,
      };

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _patientId = e['patient'] as int?;
      _patientLabel = '${e['patient_name'] ?? ''}';
      _caseReportId = e['case_report'] as int?;
      _appointmentId = e['appointment'] as int?;
      _complaint.text = '${e['chief_complaint'] ?? ''}';
      _region = '${e['region'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _vitals.forEach((key, c) {
        if (e[key] != null) c.text = '${e[key]}';
      });
    }
    _loadDiseases();
    if (_patientId != null) _loadCases(_patientId!);
  }

  Future<void> _loadDiseases() async {
    try {
      final rows = await api.getList('/api/diseases/');
      if (mounted) {
        setState(() => _diseases = rows.cast<Map<String, dynamic>>());
      }
    } catch (_) {
      // The diagnosis is optional; an empty catalog just hides the picker.
    }
  }

  /// The patient's own case reports, and the diagnosis of the one this visit is
  /// already linked to — so editing shows the diagnosis instead of blanking it.
  Future<void> _loadCases(int patientId) async {
    try {
      final rows = await api.getList('/api/case-reports/', {'patient': '$patientId'});
      if (!mounted) return;
      final cases = rows.cast<Map<String, dynamic>>();
      final linked = cases.where((c) => c['id'] == _caseReportId).firstOrNull;
      setState(() {
        _cases = cases;
        if (linked != null) {
          _diseaseId = linked['disease'] as int?;
          _severity = '${linked['severity'] ?? _severity}';
        }
      });
    } catch (_) {
      // Same as above: no cases just means no "add to a case" choice.
    }
  }

  /// File or update the case report that carries this visit's diagnosis, and
  /// return the id to link. Null when no diagnosis was entered — a visit that
  /// reached none is still a visit.
  Future<int?> _settleDiagnosis() async {
    if (_diseaseId == null) return _caseReportId;
    final body = {
      'patient': _patientId,
      'disease': _diseaseId,
      'severity': _severity,
      'region': _region,
    };
    if (_caseReportId != null) {
      // Adding to the case already linked: one illness stays one case report,
      // which is what the outcome and the surveillance rollups count.
      await api.patch('/api/case-reports/$_caseReportId/', body);
      return _caseReportId;
    }
    final created = await api.post('/api/case-reports/', body);
    return (created as Map)['id'] as int?;
  }

  @override
  void dispose() {
    for (final c in [_complaint, _notes, ..._vitals.values]) {
      c.dispose();
    }
    super.dispose();
  }

  /// A typed vital, or null when the field was left blank — an unrecorded
  /// reading is not a zero one.
  Object? _numOrNull(TextEditingController c) {
    final t = c.text.trim();
    return t.isEmpty ? null : num.tryParse(t);
  }

  Future<void> _submit() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final caseReportId = await _settleDiagnosis();
      final body = <String, dynamic>{
        'patient': _patientId,
        'case_report': caseReportId,
        'appointment': _appointmentId,
        'chief_complaint': _complaint.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
        for (final e in _vitals.entries) e.key: _numOrNull(e.value),
      };
      if (_isEdit) {
        await api.patch('/api/consultations/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/consultations/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _vitalField(String key) => TextField(
        controller: _vitals[key],
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(labelText: _vitalFields[key]),
      );

  /// Two vitals side by side — the pairs a nurse reads together.
  Widget _vitalRow(String left, String right) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(children: [
          Expanded(child: _vitalField(left)),
          const SizedBox(width: 12),
          Expanded(child: _vitalField(right)),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _isEdit ? 'Edit consultation' : 'New consultation',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Start consultation',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _complaint,
          decoration: const InputDecoration(labelText: 'Chief complaint'),
        ),
        const SizedBox(height: 12),
        PatientPicker(
          initialId: _patientId,
          initialLabel: _patientLabel,
          onChanged: (id) => setState(() {
            _patientId = id;
            // The rows offered below are that patient's, so a changed patient
            // invalidates whatever was picked from them.
            _caseReportId = null;
            _appointmentId = null;
            _cases = const [];
            if (id != null) _loadCases(id);
          }),
        ),
        const SizedBox(height: 12),
        // The diagnosis. Saving it files a case report — the row the outcome,
        // the prescriptions and the surveillance rollups all hang off.
        if (_diseases.isNotEmpty) ...[
          SearchableDropdown<int?>(
            initialValue: _diseaseId,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Diagnosis (optional)',
              helperText: 'Filed as a case report for this visit',
            ),
            items: [
              const DropdownMenuItem(value: null, child: Text('Not diagnosed yet')),
              for (final d in _diseases)
                DropdownMenuItem(
                    value: d['id'] as int, child: Text('${d['name']}')),
            ],
            onChanged: (v) => setState(() => _diseaseId = v),
          ),
          const SizedBox(height: 12),
          if (_diseaseId != null) ...[
            SearchableDropdown<String>(
              initialValue: _severity,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Severity'),
              items: [
                for (final s in _severities)
                  DropdownMenuItem(value: s, child: Text(s)),
              ],
              onChanged: (v) => setState(() => _severity = v!),
            ),
            const SizedBox(height: 12),
          ],
        ],
        // Linking an existing case is how a return visit for the same illness
        // stays one case report; leaving it unlinked files a new one from the
        // diagnosis above. Only offered once a patient is linked: the lists
        // below are theirs.
        if (_patientId != null) ...[
          if (_cases.isNotEmpty) ...[
            SearchableDropdown<int?>(
              initialValue:
                  _cases.any((c) => c['id'] == _caseReportId) ? _caseReportId : null,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Existing case (optional)',
                helperText: 'Adds this visit to a case already open',
              ),
              items: [
                const DropdownMenuItem(value: null, child: Text('Not linked')),
                for (final c in _cases)
                  DropdownMenuItem(
                    value: c['id'] as int,
                    child: Text(
                        '${c['disease_name'] ?? 'Case'} · ${c['outcome'] ?? ''}'),
                  ),
              ],
              onChanged: (v) => setState(() {
                _caseReportId = v;
                // Show that case's own diagnosis, so saving cannot silently
                // rewrite it with whatever was picked before.
                final picked = _cases.where((c) => c['id'] == v).firstOrNull;
                if (picked != null) {
                  _diseaseId = picked['disease'] as int?;
                  _severity = '${picked['severity'] ?? _severity}';
                }
              }),
            ),
            const SizedBox(height: 12),
          ],
          // Scheduled only: a walk-in has no booking, and a completed or
          // cancelled one is not what this visit is against.
          _LinkedRowPicker(
            key: ValueKey('appointment-$_patientId'),
            path: '/api/appointments/',
            query: {'patient': '$_patientId', 'status': 'scheduled'},
            label: 'Appointment (optional)',
            labelOf: (r) {
              final reason = '${r['reason'] ?? ''}'.trim();
              final mode = '${r['mode']}' == 'telemedicine' ? 'tele' : 'in-person';
              return '${reason.isEmpty ? 'Appointment #${r['id']}' : reason} · $mode';
            },
            initialId: _appointmentId,
            onChanged: (id) => _appointmentId = id,
          ),
          const SizedBox(height: 12),
        ],
        _vitalRow('temperature_c', 'pulse_bpm'),
        _vitalRow('systolic_bp', 'diastolic_bp'),
        _vitalRow('respiratory_rate', 'oxygen_saturation'),
        _vitalRow('weight_kg', 'height_cm'),
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

/// Links this consultation to one of the patient's own rows — a case report or
/// a booking. Hides itself when the patient has none, which is the normal state
/// early in a visit, so it never blocks the form.
class _LinkedRowPicker extends StatefulWidget {
  final String path; // list endpoint, e.g. /api/case-reports/
  final Map<String, String> query; // patient filter, plus any narrowing
  final String label;
  final String Function(Map<String, dynamic> row) labelOf;
  final int? initialId;
  final ValueChanged<int?> onChanged;

  const _LinkedRowPicker({
    super.key,
    required this.path,
    required this.query,
    required this.label,
    required this.labelOf,
    required this.initialId,
    required this.onChanged,
  });

  @override
  State<_LinkedRowPicker> createState() => _LinkedRowPickerState();
}

class _LinkedRowPickerState extends State<_LinkedRowPicker> {
  late Future<List<dynamic>> _future;
  int? _id;

  @override
  void initState() {
    super.initState();
    _id = widget.initialId;
    _future = api.getList(widget.path, widget.query);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<dynamic>>(
      future: _future,
      builder: (context, snap) {
        final rows = (snap.data ?? []).cast<Map<String, dynamic>>();
        if (rows.isEmpty) return const SizedBox.shrink();
        return SearchableDropdown<int?>(
          // The linked row can be outside the offered list (a booking already
          // marked completed); showing it as picked would be a lie.
          initialValue: rows.any((r) => r['id'] == _id) ? _id : null,
          isExpanded: true,
          decoration: InputDecoration(labelText: widget.label),
          items: [
            const DropdownMenuItem(value: null, child: Text('Not linked')),
            for (final r in rows)
              DropdownMenuItem(
                  value: r['id'] as int, child: Text(widget.labelOf(r))),
          ],
          onChanged: (v) {
            _id = v;
            widget.onChanged(v);
          },
        );
      },
    );
  }
}
