import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Immunization registry — GET/POST /api/immunizations/.
/// One row per vaccine dose administered; coverage analysis groups by vaccine,
/// region and age band.
class ImmunizationsScreen extends StatelessWidget {
  const ImmunizationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/immunizations/',
      fabLabel: 'Record dose',
      emptyIcon: Icons.vaccines_outlined,
      emptyTitle: 'No doses recorded yet',
      emptyMessage: 'Tap "Record dose" to add the first one.',
      savedMessage: 'Dose recorded.',
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
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
    final vaccine = '${row['vaccine'] ?? ''}'.trim();
    final dose = row['dose_number'] ?? 1;
    final age = '${row['patient_age_group'] ?? ''}'.trim();
    final reporter = '${row['reporter_name'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(vaccine.isEmpty ? 'Dose #${row['id']}' : vaccine,
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(text: 'dose $dose', color: EnhancedTheme.primaryTeal),
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
          const SizedBox(height: 8),
          Text(
            [if (age.isNotEmpty) 'Age $age', if (reporter.isNotEmpty) 'by $reporter'].join('  ·  '),
            style: TextStyle(color: context.hintColor, fontSize: 11),
          ),
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/immunizations/${row['id']}/',
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
  final _vaccine = TextEditingController();
  final _dose = TextEditingController(text: '1');
  final _age = TextEditingController();
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
      _vaccine.text = '${e['vaccine'] ?? ''}';
      _dose.text = '${e['dose_number'] ?? 1}';
      _age.text = '${e['patient_age_group'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _vaccine.dispose();
    _dose.dispose();
    _age.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_vaccine.text.trim().isEmpty) {
      setState(() => _error = 'Enter a vaccine name.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'vaccine': _vaccine.text.trim(),
        'dose_number': int.tryParse(_dose.text.trim()) ?? 1,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/immunizations/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/immunizations/', body);
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
      title: _isEdit ? 'Edit dose' : 'Record a dose',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit dose',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _vaccine,
          decoration: const InputDecoration(labelText: 'Vaccine (e.g. BCG, Measles, OPV)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _dose,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Dose number'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _age,
          decoration: const InputDecoration(labelText: 'Patient age group (e.g. 0-5)'),
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
