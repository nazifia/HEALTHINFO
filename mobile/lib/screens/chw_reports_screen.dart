import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Community health worker reports — GET/POST /api/chw-reports/.
/// Out-of-facility care: antenatal, newborns, malnutrition, home deaths.
class ChwReportsScreen extends StatelessWidget {
  const ChwReportsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/chw-reports/',
      fabLabel: 'Add report',
      emptyIcon: Icons.groups_outlined,
      emptyTitle: 'No field reports yet',
      emptyMessage: 'Tap "Add report" to file the first one.',
      savedMessage: 'Report saved.',
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

const _types = ['pregnancy', 'newborn', 'malnutrition', 'death', 'other'];

const _typeColor = {
  'pregnancy': EnhancedTheme.accentPurple,
  'newborn': EnhancedTheme.accentCyan,
  'malnutrition': EnhancedTheme.accentOrange,
  'death': EnhancedTheme.errorRed,
  'other': EnhancedTheme.primaryTeal,
};

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final VoidCallback edit;
  const _Card({required this.row, required this.reload, required this.edit});

  @override
  Widget build(BuildContext context) {
    final type = '${row['report_type'] ?? ''}';
    final danger = row['danger_signs'] == true;
    final referred = row['referred'] == true;
    final reporter = '${row['reporter_name'] ?? ''}'.trim();
    final age = '${row['patient_age_group'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(type.isEmpty ? 'Report #${row['id']}' : type,
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(text: type, color: _typeColor[type] ?? EnhancedTheme.primaryTeal),
            if (danger) ...[
              const SizedBox(width: 6),
              const ReportBadge(text: 'danger', color: EnhancedTheme.errorRed),
            ],
            if (referred) ...[
              const SizedBox(width: 6),
              const ReportBadge(text: 'referred', color: EnhancedTheme.infoBlue),
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
          const SizedBox(height: 8),
          Text(
            [if (age.isNotEmpty) 'Age $age', if (reporter.isNotEmpty) 'by $reporter'].join('  ·  '),
            style: TextStyle(color: context.hintColor, fontSize: 11),
          ),
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/chw-reports/${row['id']}/',
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
  final _age = TextEditingController();
  final _notes = TextEditingController();
  String _type = 'pregnancy';
  bool _danger = false;
  bool _referred = false;
  String _region = '';
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      if (_types.contains(e['report_type'])) _type = e['report_type'];
      _danger = e['danger_signs'] == true;
      _referred = e['referred'] == true;
      _age.text = '${e['patient_age_group'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
    }
  }

  @override
  void dispose() {
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
        'report_type': _type,
        'danger_signs': _danger,
        'referred': _referred,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/chw-reports/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/chw-reports/', body);
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
      title: _isEdit ? 'Edit field report' : 'New field report',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit report',
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _type,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Report type'),
          items: [for (final k in _types) DropdownMenuItem(value: k, child: Text(k))],
          onChanged: (v) => setState(() => _type = v!),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Danger signs'),
          subtitle: const Text('Needs urgent attention'),
          value: _danger,
          onChanged: (v) => setState(() => _danger = v),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Referred to facility'),
          value: _referred,
          onChanged: (v) => setState(() => _referred = v),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _age,
          decoration: const InputDecoration(labelText: 'Age group (e.g. 0-1, 19-40)'),
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
