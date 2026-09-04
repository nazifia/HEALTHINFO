import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/searchable_dropdown.dart';
import 'report_scaffold.dart';
import 'drug_orders_screen.dart';
import 'patient_access_log_screen.dart';
import 'prescriptions_screen.dart';

/// Patient registry — GET/POST /api/patients/.
/// The only screen that shows identifying data; the backend limits it to
/// clinical staff, so non-clinical members get a 403 here by design.
/// Tapping a card opens the patient's cross-module history.
class PatientsScreen extends StatelessWidget {
  const PatientsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/patients/',
      fabLabel: 'Register patient',
      emptyIcon: Icons.people_outline,
      emptyTitle: 'No patients yet',
      emptyMessage: 'Tap "Register patient" to add the first one.',
      savedMessage: 'Patient saved.',
      searchHint: 'Search name, hospital number or phone',
      // Server-side, so the counts in the header describe the filtered set.
      filters: const [
        ReportFilter(
            param: 'patient_type', anyLabel: 'Any type', options: patientTypes),
        ReportFilter(param: 'status', anyLabel: 'Any status', options: {
          'active': 'Active',
          'inactive': 'Inactive',
          'deceased': 'Deceased',
        }),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _Card(row: row, edit: edit),
      form: (existing) => _Form(existing: existing),
      onTap: (row) => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => PatientDetailScreen(patient: row)),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final female = countEq(items, 'sex', 'F');
    final male = countEq(items, 'sex', 'M');
    final byAge = countBy(items, 'age_group');
    final nhia = countEq(items, 'patient_type', 'nhia');
    final byType = countBy(items, 'patient_type_display');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.people_outline,
            title: 'Patients',
            subtitle: '${items.length} patient${items.length == 1 ? '' : 's'}',
            color: EnhancedTheme.primaryTeal,
          ),
          KpiRow(tiles: [
            KpiTile(
                icon: Icons.people_outline,
                label: 'Total',
                value: '${items.length}',
                color: EnhancedTheme.primaryTeal),
            KpiTile(
                icon: Icons.female_outlined,
                label: 'Female',
                value: '$female',
                color: EnhancedTheme.accentPurple),
            KpiTile(
                icon: Icons.male_outlined,
                label: 'Male',
                value: '$male',
                color: EnhancedTheme.accentCyan),
            KpiTile(
                icon: Icons.verified_user_outlined,
                label: 'NHIA',
                value: '$nhia',
                color: EnhancedTheme.accentPurple),
          ]),
          const SizedBox(height: 10),
          if (byAge.isNotEmpty)
            StatSection(
              icon: Icons.bar_chart_rounded,
              heading: 'By age group',
              child: MiniBarChart(rows: byAge),
            ),
          if (byType.length > 1) ...[
            const SizedBox(height: 10),
            StatSection(
              icon: Icons.account_balance_wallet_outlined,
              heading: 'By patient type',
              child: MiniBarChart(rows: byType),
            ),
          ],
        ],
      ),
    );
  }
}

const _sexes = ['M', 'F', 'other'];
const _statuses = ['active', 'inactive', 'deceased'];
const _bloodGroups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const _genotypes = ['AA', 'AS', 'AC', 'SS', 'SC'];

/// How the patient's care is paid for — value to label, mirroring
/// `Patient.PatientType` on the backend. The value goes on the wire; the label
/// is what reception reads.
const patientTypes = <String, String>{
  'regular': 'Regular',
  'nhia': 'NHIA',
  'private': 'Private Pay',
  'insurance': 'Private Insurance',
  'corporate': 'Corporate',
  'staff': 'Staff',
  'dependant': 'Dependant',
  'emergency': 'Emergency',
  'retainership': 'Retainership',
};

const _statusColor = {
  'active': EnhancedTheme.successGreen,
  'inactive': Colors.grey,
  'deceased': EnhancedTheme.errorRed,
  'merged': Colors.blueGrey,
};

/// The same rules the API enforces, checked before the round trip so the user
/// sees them next to the fields. Returns null when the form is submittable.
///
/// Kept a plain function rather than a Form/validator: the sheet has no
/// FormState and these are two cross-field rules, not per-field ones.
String? patientFormError({
  required String firstName,
  required String lastName,
  required String patientType,
  required String nhisNumber,
}) {
  if (firstName.trim().isEmpty || lastName.trim().isEmpty) {
    return 'First and last name are required.';
  }
  // An NHIA patient is only NHIA if the scheme can be billed.
  if (patientType == 'nhia' && nhisNumber.trim().isEmpty) {
    return 'NHIS number is required for NHIA patients.';
  }
  return null;
}

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback edit;
  const _Card({required this.row, required this.edit});

  @override
  Widget build(BuildContext context) {
    final status = '${row['status'] ?? ''}';
    final age = row['age'];
    final sex = '${row['sex'] ?? ''}';
    final type = '${row['patient_type'] ?? ''}';
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text('${row['full_name'] ?? ''}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            // Regular is the default and the majority — badging it would just
            // be noise, so only the exceptions get called out.
            if (type.isNotEmpty && type != 'regular') ...[
              ReportBadge(
                  text: '${row['patient_type_display'] ?? patientTypes[type] ?? type}',
                  color: row['is_nhia'] == true
                      ? EnhancedTheme.accentPurple
                      : EnhancedTheme.accentCyan),
              const SizedBox(width: 6),
            ],
            ReportBadge(
                text: status, color: _statusColor[status] ?? EnhancedTheme.primaryTeal),
            IconButton(
              visualDensity: VisualDensity.compact,
              icon: Icon(Icons.edit_outlined, size: 18, color: context.hintColor),
              onPressed: edit,
            ),
          ]),
          const SizedBox(height: 6),
          Text(
            [
              '${row['hospital_number'] ?? ''}',
              if (sex.isNotEmpty) sex,
              if (age != null) '${age}y',
              if ('${row['region'] ?? ''}'.isNotEmpty) '${row['region']}',
            ].join(' · '),
            style: TextStyle(color: context.hintColor, fontSize: 12),
          ),
          if ('${row['allergies'] ?? ''}'.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Row(children: [
              const Icon(Icons.warning_amber_outlined,
                  size: 14, color: EnhancedTheme.errorRed),
              const SizedBox(width: 4),
              Expanded(
                child: Text('Allergies: ${row['allergies']}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: EnhancedTheme.errorRed, fontSize: 12)),
              ),
            ]),
          ],
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
  final _first = TextEditingController();
  final _last = TextEditingController();
  final _other = TextEditingController();
  final _hospitalNumber = TextEditingController();
  final _phone = TextEditingController();
  final _address = TextEditingController();
  final _allergies = TextEditingController();
  final _nhis = TextEditingController();
  final _kinName = TextEditingController();
  final _kinPhone = TextEditingController();
  final _kinRelationship = TextEditingController();
  final _notes = TextEditingController();

  String _sex = 'F';
  String _status = 'active';
  String _patientType = 'regular';
  String? _bloodGroup;
  String? _genotype;
  String _region = '';
  DateTime? _dob;
  DateTime? _dod;
  bool _consent = false;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e == null) return;
    if (_sexes.contains(e['sex'])) _sex = e['sex'];
    // Takes the status as-is, even one the dropdown doesn't offer ('merged'),
    // so editing a record can never silently change what it is.
    _status = '${e['status'] ?? _status}';
    if (patientTypes.containsKey(e['patient_type'])) {
      _patientType = e['patient_type'];
    }
    if (_bloodGroups.contains(e['blood_group'])) _bloodGroup = e['blood_group'];
    if (_genotypes.contains(e['genotype'])) _genotype = e['genotype'];
    _first.text = '${e['first_name'] ?? ''}';
    _last.text = '${e['last_name'] ?? ''}';
    _other.text = '${e['other_names'] ?? ''}';
    _hospitalNumber.text = '${e['hospital_number'] ?? ''}';
    _phone.text = '${e['phone'] ?? ''}';
    _address.text = '${e['address'] ?? ''}';
    _allergies.text = '${e['allergies'] ?? ''}';
    _nhis.text = '${e['nhis_number'] ?? ''}';
    _kinName.text = '${e['next_of_kin_name'] ?? ''}';
    _kinPhone.text = '${e['next_of_kin_phone'] ?? ''}';
    _kinRelationship.text = '${e['next_of_kin_relationship'] ?? ''}';
    _notes.text = '${e['notes'] ?? ''}';
    _region = '${e['region'] ?? ''}';
    _consent = e['consent_given'] == true;
    _dob = DateTime.tryParse('${e['date_of_birth'] ?? ''}');
    _dod = DateTime.tryParse('${e['date_of_death'] ?? ''}');
  }

  @override
  void dispose() {
    for (final c in [_first, _last, _other, _hospitalNumber, _phone, _address,
                     _allergies, _nhis, _kinName, _kinPhone, _kinRelationship,
                     _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickDob() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _dob ?? DateTime(now.year - 20),
      firstDate: DateTime(now.year - 120),
      lastDate: now,
    );
    if (picked != null) setState(() => _dob = picked);
  }

  Future<void> _pickDod() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _dod ?? now,
      firstDate: _dob ?? DateTime(now.year - 120),
      lastDate: now,
    );
    if (picked != null) setState(() => _dod = picked);
  }

  String _dateText(DateTime? d) => d == null
      ? 'Not set'
      : '${d.year}-${d.month.toString().padLeft(2, '0')}-'
          '${d.day.toString().padLeft(2, '0')}';

  String get _dobText => _dateText(_dob);

  Future<void> _submit() async {
    final problem = patientFormError(
      firstName: _first.text,
      lastName: _last.text,
      patientType: _patientType,
      nhisNumber: _nhis.text,
    );
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'first_name': _first.text.trim(),
        'last_name': _last.text.trim(),
        'other_names': _other.text.trim(),
        'hospital_number': _hospitalNumber.text.trim(),
        'patient_type': _patientType,
        'sex': _sex,
        'date_of_birth': _dob == null ? null : _dobText,
        'phone': _phone.text.trim(),
        'address': _address.text.trim(),
        'region': _region,
        'blood_group': _bloodGroup ?? '',
        'genotype': _genotype ?? '',
        'allergies': _allergies.text.trim(),
        'nhis_number': _nhis.text.trim(),
        'next_of_kin_name': _kinName.text.trim(),
        'next_of_kin_phone': _kinPhone.text.trim(),
        'next_of_kin_relationship': _kinRelationship.text.trim(),
        'status': _status,
        // Only a deceased patient carries one; anything else clears it, which
        // is how the backend lets a wrongly-marked patient come back.
        'date_of_death':
            _status == 'deceased' && _dod != null ? _dateText(_dod) : null,
        'consent_given': _consent,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/patients/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/patients/', body);
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
      title: _isEdit ? 'Edit patient' : 'Register patient',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Register',
      onSubmit: _submit,
      children: [
        Row(children: [
          Expanded(
            child: TextField(
              controller: _first,
              decoration: const InputDecoration(labelText: 'First name *'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _last,
              decoration: const InputDecoration(labelText: 'Last name *'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _other,
          decoration: const InputDecoration(labelText: 'Other names'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _hospitalNumber,
          decoration: const InputDecoration(
            labelText: 'Hospital number',
            helperText: 'Leave blank to generate one from the patient type',
          ),
        ),
        const SizedBox(height: 12),
        SearchableDropdown<String>(
          initialValue: _patientType,
          isExpanded: true,
          decoration: const InputDecoration(
            labelText: 'Patient type',
            helperText: 'Decides the billing route',
          ),
          items: [
            for (final t in patientTypes.entries)
              DropdownMenuItem(value: t.key, child: Text(t.value)),
          ],
          // Rebuilds the NHIS field below, which becomes required for NHIA.
          onChanged: (v) => setState(() => _patientType = v!),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: SearchableDropdown<String>(
              initialValue: _sex,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Sex'),
              items: [
                for (final s in _sexes) DropdownMenuItem(value: s, child: Text(s)),
              ],
              onChanged: (v) => setState(() => _sex = v!),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: InkWell(
              onTap: _pickDob,
              child: InputDecorator(
                decoration: const InputDecoration(labelText: 'Date of birth'),
                child: Text(_dobText,
                    style: TextStyle(
                        color: _dob == null ? context.hintColor : context.labelColor)),
              ),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
              labelText: 'Phone', hintText: '08031234567'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: SearchableDropdown<String>(
              initialValue: _bloodGroup,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Blood group'),
              items: [
                for (final b in _bloodGroups)
                  DropdownMenuItem(value: b, child: Text(b)),
              ],
              onChanged: (v) => setState(() => _bloodGroup = v),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SearchableDropdown<String>(
              initialValue: _genotype,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Genotype'),
              items: [
                for (final g in _genotypes)
                  DropdownMenuItem(value: g, child: Text(g)),
              ],
              onChanged: (v) => setState(() => _genotype = v),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _allergies,
          decoration: const InputDecoration(
              labelText: 'Allergies', hintText: 'e.g. penicillin'),
        ),
        const SizedBox(height: 12),
        RegionPicker(
            initial: _region.isEmpty ? null : _region, onChanged: (r) => _region = r),
        const SizedBox(height: 12),
        TextField(
          controller: _address,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Address'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _nhis,
          decoration: InputDecoration(
            labelText:
                _patientType == 'nhia' ? 'NHIS number *' : 'NHIS number',
            helperText: _patientType == 'nhia'
                ? 'Required — this is what makes the exemption claimable'
                : null,
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _kinName,
          decoration: const InputDecoration(labelText: 'Next of kin'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _kinPhone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Kin phone'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _kinRelationship,
              decoration: const InputDecoration(labelText: 'Relationship'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        SearchableDropdown<String>(
          initialValue: _status,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Status'),
          items: [
            for (final s in {..._statuses, _status})
              DropdownMenuItem(value: s, child: Text(s)),
          ],
          onChanged: (v) => setState(() => _status = v!),
        ),
        if (_status == 'deceased') ...[
          const SizedBox(height: 12),
          InkWell(
            onTap: _pickDod,
            child: InputDecorator(
              decoration: const InputDecoration(labelText: 'Date of death'),
              child: Text(_dateText(_dod),
                  style: TextStyle(
                      color: _dod == null ? context.hintColor : context.labelColor)),
            ),
          ),
        ],
        const SizedBox(height: 4),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: _consent,
          onChanged: (v) => setState(() => _consent = v ?? false),
          title: Text('Consent given to store personal data',
              style: TextStyle(color: context.labelColor, fontSize: 14)),
          controlAffinity: ListTileControlAffinity.leading,
        ),
        TextField(
          controller: _notes,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Notes'),
        ),
      ],
    );
  }
}

/// One patient's record: demographics plus everything filed against them across
/// the clinical modules — GET /api/patients/{id}/history/.
class PatientDetailScreen extends StatefulWidget {
  final Map<String, dynamic> patient;
  const PatientDetailScreen({super.key, required this.patient});

  @override
  State<PatientDetailScreen> createState() => _PatientDetailScreenState();
}

class _PatientDetailScreenState extends State<PatientDetailScreen> {
  late Future<dynamic> _future;

  // Response key -> (heading, icon, field to show as the row's title).
  static const _sections = {
    'consultations':
        ('Consultations', Icons.medical_information_outlined, 'chief_complaint'),
    'case_reports': ('Case reports', Icons.assignment_outlined, 'disease_name'),
    'adverse_reactions':
        ('Adverse reactions', Icons.medication_liquid_outlined, 'reaction'),
    'lab_results': ('Lab results', Icons.science_outlined, 'lab_test_name'),
    'immunizations': ('Immunizations', Icons.vaccines_outlined, 'vaccine'),
    'vital_events': ('Vital events', Icons.child_friendly_outlined, 'event_type'),
    'chw_reports': ('CHW reports', Icons.groups_outlined, 'report_type'),
    'prescriptions':
        ('Prescriptions', Icons.medication_outlined, 'medication_name'),
    'insurance_claims':
        ('Insurance claims', Icons.receipt_long_outlined, 'diagnosis_name'),
    'appointments': ('Appointments', Icons.event_outlined, 'reason'),
  };

  @override
  void initState() {
    super.initState();
    _future = api.get('/api/patients/${widget.patient['id']}/history/');
  }

  void _say(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  /// Absorb a duplicate record into this one — the same person registered
  /// twice. The duplicate is found by the hospital number reception has in
  /// front of them; the API does the moving and keeps it as a pointer here.
  Future<void> _mergeDuplicate() async {
    final number = TextEditingController();
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Merge a duplicate'),
        content: TextField(
          controller: number,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Duplicate hospital number',
            helperText: 'Its records move to this one. Cannot be undone.',
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Merge')),
        ],
      ),
    );
    final wanted = number.text.trim();
    if (go != true || wanted.isEmpty) return;
    final id = widget.patient['id'];
    try {
      final rows = await api.getList('/api/patients/', {'search': wanted});
      final match = rows.cast<Map<String, dynamic>?>().firstWhere(
            (r) => '${r?['hospital_number']}' == wanted && r?['id'] != id,
            orElse: () => null,
          );
      if (match == null) {
        _say('No other patient with hospital number $wanted');
        return;
      }
      final result = await api.post('/api/patients/$id/merge/',
          {'source': match['id']});
      final moved = (result['moved'] as Map).values
          .fold<int>(0, (sum, n) => sum + (n as int));
      _say('Merged $wanted — $moved record(s) moved here');
      setState(() { _future = api.get('/api/patients/$id/history/'); });
    } catch (e) {
      _say('$e');
    }
  }

  /// Prescribe off this record: the clinician's own order, filed against the
  /// patient and waiting for whoever dispenses it.
  Future<void> _prescribe() async {
    if (!await prescribeFor(context, widget.patient)) return;
    _say('Order written for ${widget.patient['full_name']}.');
    setState(() {
      _future = api.get('/api/patients/${widget.patient['id']}/history/');
    });
  }

  /// Write a counter script for this patient without hunting them down again
  /// on the pharmacy screen. It reaches their history once the counter
  /// dispenses off it — that is the point the drug actually left the shelf.
  Future<void> _writeScript() async {
    if (!await writeScriptFor(context, widget.patient)) return;
    _say('Script written. It lands here once the counter dispenses it.');
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.patient;
    return Scaffold(
      appBar: AppBar(
        title: Text('${p['full_name'] ?? 'Patient'}'),
        actions: [
          // Each button is gated the way its endpoint is: clinical cadres
          // prescribe, pharmacy staff write counter scripts, and the read
          // trail and merging are admin-only. Nobody is offered a 403.
          FutureBuilder<String?>(
            future: api.myRole(),
            builder: (context, snap) {
              const admins = {'tenant_admin', 'super_admin'};
              final role = snap.data;
              return Row(mainAxisSize: MainAxisSize.min, children: [
                if (api.roleCanReport(role))
                  IconButton(
                    tooltip: 'Prescribe medications',
                    icon: const Icon(Icons.medication_outlined),
                    onPressed: _prescribe,
                  ),
                if (isPharmacyStaff(role))
                  IconButton(
                    tooltip: 'Write a counter script',
                    icon: const Icon(Icons.description_outlined),
                    onPressed: _writeScript,
                  ),
                if (admins.contains(role)) IconButton(
                  tooltip: 'Merge a duplicate into this record',
                  icon: const Icon(Icons.merge_outlined),
                  onPressed: _mergeDuplicate,
                ),
                if (admins.contains(role)) IconButton(
                  tooltip: 'Who accessed this record',
                  icon: const Icon(Icons.privacy_tip_outlined),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) =>
                          PatientAccessLogScreen(patientId: p['id'] as int?),
                    ),
                  ),
                ),
              ]);
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _Details(patient: p),
          const SizedBox(height: 12),
          FutureBuilder<dynamic>(
            future: _future,
            builder: (context, snap) {
              if (snap.connectionState == ConnectionState.waiting) {
                return const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                      child: CircularProgressIndicator(
                          color: EnhancedTheme.primaryTeal)),
                );
              }
              if (snap.hasError) {
                return EmptyState(
                  icon: Icons.error_outline,
                  title: 'Could not load history',
                  message: '${snap.error}',
                  color: EnhancedTheme.errorRed,
                );
              }
              final data = (snap.data as Map).cast<String, dynamic>();
              final blocks = <Widget>[];
              for (final entry in _sections.entries) {
                final rows = (data[entry.key] as List? ?? [])
                    .cast<Map<String, dynamic>>();
                if (rows.isEmpty) continue;
                final (heading, icon, titleKey) = entry.value;
                blocks.add(_HistoryBlock(
                    heading: heading, icon: icon, titleKey: titleKey, rows: rows));
              }
              if (blocks.isEmpty) {
                return const EmptyState(
                  icon: Icons.history,
                  title: 'No records yet',
                  message: 'Reports linked to this patient will show up here.',
                );
              }
              return Column(children: blocks);
            },
          ),
        ],
      ),
    );
  }
}

class _Details extends StatelessWidget {
  final Map<String, dynamic> patient;
  const _Details({required this.patient});

  @override
  Widget build(BuildContext context) {
    final rows = <(String, String)>[
      ('Hospital number', '${patient['hospital_number'] ?? ''}'),
      ('Patient type', '${patient['patient_type_display'] ?? ''}'),
      ('Sex', '${patient['sex'] ?? ''}'),
      ('Date of birth', '${patient['date_of_birth'] ?? '—'}'),
      ('Date of death', '${patient['date_of_death'] ?? ''}'),
      ('Age', patient['age'] == null ? '—' : '${patient['age']}'),
      ('Phone', '${patient['phone'] ?? ''}'),
      ('Region', '${patient['region'] ?? ''}'),
      ('Blood group', '${patient['blood_group'] ?? ''}'),
      ('Genotype', '${patient['genotype'] ?? ''}'),
      ('Allergies', '${patient['allergies'] ?? ''}'),
      ('NHIS', '${patient['nhis_number'] ?? ''}'),
      ('Next of kin',
          '${patient['next_of_kin_name'] ?? ''} ${patient['next_of_kin_phone'] ?? ''}'),
      ('Consent', patient['consent_given'] == true ? 'Given' : 'Not recorded'),
      // Only set on a duplicate that was absorbed — says where its records went.
      ('Merged into', '${patient['merged_into_number'] ?? ''}'),
    ];
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (label, value) in rows)
            if (value.trim().isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 120,
                      child: Text(label,
                          style:
                              TextStyle(color: context.hintColor, fontSize: 12)),
                    ),
                    Expanded(
                      child: Text(value,
                          style: TextStyle(
                              color: context.labelColor,
                              fontSize: 13,
                              fontWeight: FontWeight.w600)),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }
}

class _HistoryBlock extends StatelessWidget {
  final String heading;
  final IconData icon;
  final String titleKey;
  final List<Map<String, dynamic>> rows;

  const _HistoryBlock({
    required this.heading,
    required this.icon,
    required this.titleKey,
    required this.rows,
  });

  @override
  Widget build(BuildContext context) {
    return StatSection(
      icon: icon,
      heading: '$heading (${rows.length})',
      child: Column(
        children: [
          for (final r in rows)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(
                '${r[titleKey] ?? ''}'.trim().isEmpty
                    ? '#${r['id']}'
                    : '${r[titleKey]}',
                style: TextStyle(color: context.labelColor, fontSize: 14),
              ),
              subtitle: Text('${r['created_at'] ?? ''}'.split('T').first,
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            ),
        ],
      ),
    );
  }
}
