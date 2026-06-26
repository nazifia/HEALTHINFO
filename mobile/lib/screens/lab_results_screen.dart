import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Laboratory results — GET/POST /api/lab-results/.
/// Lab-confirmed surveillance plus the antimicrobial-resistance (AMR) signal:
/// fill organism + antibiotic + susceptibility and the row is one AMR data point.
class LabResultsScreen extends StatelessWidget {
  const LabResultsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/lab-results/',
      fabLabel: 'Add result',
      emptyIcon: Icons.science_outlined,
      emptyTitle: 'No lab results yet',
      emptyMessage: 'Tap "Add result" to file the first one.',
      savedMessage: 'Result saved.',
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

const _flags = ['normal', 'abnormal', 'critical'];
const _susceptibility = ['', 'susceptible', 'intermediate', 'resistant'];

const _flagColor = {
  'normal': EnhancedTheme.successGreen,
  'abnormal': Colors.orange,
  'critical': EnhancedTheme.errorRed,
};
const _susColor = {
  'susceptible': EnhancedTheme.successGreen,
  'intermediate': Colors.orange,
  'resistant': EnhancedTheme.errorRed,
};

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final VoidCallback edit;
  const _Card({required this.row, required this.reload, required this.edit});

  @override
  Widget build(BuildContext context) {
    final flag = '${row['flag'] ?? ''}';
    final organism = '${row['organism'] ?? ''}'.trim();
    final antibiotic = '${row['antibiotic'] ?? ''}'.trim();
    final sus = '${row['susceptibility'] ?? ''}'.trim();
    final test = '${row['lab_test_name'] ?? ''}'.trim();
    final value = '${row['value'] ?? ''}'.trim();
    final title = test.isNotEmpty
        ? test
        : (organism.isNotEmpty ? organism : 'Result #${row['id']}');
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(title,
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(text: flag, color: _flagColor[flag] ?? EnhancedTheme.primaryTeal),
            if (sus.isNotEmpty) ...[
              const SizedBox(width: 6),
              ReportBadge(text: sus, color: _susColor[sus] ?? EnhancedTheme.accentCyan),
            ],
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
          if (value.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(value, style: TextStyle(color: context.subLabelColor, fontSize: 13)),
          ],
          if (organism.isNotEmpty || antibiotic.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              [if (organism.isNotEmpty) organism, if (antibiotic.isNotEmpty) 'vs $antibiotic']
                  .join('  '),
              style: const TextStyle(
                  color: EnhancedTheme.accentOrange, fontWeight: FontWeight.w600, fontSize: 13),
            ),
          ],
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/lab-results/${row['id']}/',
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
  final _value = TextEditingController();
  final _organism = TextEditingController();
  final _antibiotic = TextEditingController();
  final _age = TextEditingController();
  final _notes = TextEditingController();
  String _flag = 'normal';
  String _sus = '';
  String _region = '';
  int? _labTestId;
  int? _diseaseId;
  List<Map<String, dynamic>> _labTests = [];
  List<Map<String, dynamic>> _diseases = [];
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _value.text = '${e['value'] ?? ''}';
      _organism.text = '${e['organism'] ?? ''}';
      _antibiotic.text = '${e['antibiotic'] ?? ''}';
      _age.text = '${e['patient_age_group'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      if (_flags.contains(e['flag'])) _flag = e['flag'];
      if (_susceptibility.contains(e['susceptibility'])) _sus = '${e['susceptibility'] ?? ''}';
      _region = '${e['region'] ?? ''}';
      _labTestId = e['lab_test'] as int?;
      _diseaseId = e['disease'] as int?;
    }
    _loadPickers();
  }

  Future<void> _loadPickers() async {
    try {
      final tests = await api.getList('/api/lab-tests/');
      final diseases = await api.getList('/api/diseases/');
      setState(() {
        _labTests = tests.cast<Map<String, dynamic>>();
        _diseases = diseases.cast<Map<String, dynamic>>();
      });
    } catch (_) {}
  }

  @override
  void dispose() {
    _value.dispose();
    _organism.dispose();
    _antibiotic.dispose();
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
        'lab_test': _labTestId,
        'disease': _diseaseId,
        'value': _value.text.trim(),
        'flag': _flag,
        'organism': _organism.text.trim(),
        'antibiotic': _antibiotic.text.trim(),
        'susceptibility': _sus,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/lab-results/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/lab-results/', body);
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
      title: _isEdit ? 'Edit lab result' : 'Add lab result',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit result',
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<int?>(
          initialValue: _labTestId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Lab test (optional)'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— none —')),
            for (final m in _labTests)
              DropdownMenuItem(value: m['id'] as int, child: Text('${m['name']}')),
          ],
          onChanged: (v) => setState(() => _labTestId = v),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _value,
          decoration: const InputDecoration(labelText: 'Result value (e.g. 12.3 g/dL)'),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _flag,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Flag'),
          items: [for (final f in _flags) DropdownMenuItem(value: f, child: Text(f))],
          onChanged: (v) => setState(() => _flag = v!),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int?>(
          initialValue: _diseaseId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Suspected disease (optional)'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— none —')),
            for (final d in _diseases)
              DropdownMenuItem(value: d['id'] as int, child: Text('${d['name']}')),
          ],
          onChanged: (v) => setState(() => _diseaseId = v),
        ),
        const SizedBox(height: 16),
        Text('Antimicrobial resistance (optional)',
            style: TextStyle(color: context.hintColor, fontSize: 12, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _organism,
              decoration: const InputDecoration(labelText: 'Organism'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _antibiotic,
              decoration: const InputDecoration(labelText: 'Antibiotic'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _sus,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Susceptibility'),
          items: [
            for (final s in _susceptibility)
              DropdownMenuItem(value: s, child: Text(s.isEmpty ? '— n/a —' : s)),
          ],
          onChanged: (v) => setState(() => _sus = v!),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _age,
          decoration: const InputDecoration(labelText: 'Patient age group (e.g. 0-5, 60+)'),
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
