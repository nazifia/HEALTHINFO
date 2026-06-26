import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Vital registration — GET/POST /api/vital-events/.
/// Births & deaths in one feed; deaths flagged maternal/infant drive the
/// maternal mortality ratio and infant mortality rate.
class VitalEventsScreen extends StatelessWidget {
  const VitalEventsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/vital-events/',
      fabLabel: 'Record event',
      emptyIcon: Icons.child_friendly_outlined,
      emptyTitle: 'No vital events yet',
      emptyMessage: 'Tap "Record event" to register a birth or death.',
      savedMessage: 'Event recorded.',
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

const _kinds = ['birth', 'death'];

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final VoidCallback edit;
  const _Card({required this.row, required this.reload, required this.edit});

  @override
  Widget build(BuildContext context) {
    final kind = '${row['event_type'] ?? ''}';
    final isDeath = kind == 'death';
    final cause = '${row['cause_name'] ?? ''}'.trim();
    final maternal = row['maternal_death'] == true;
    final infant = row['infant_death'] == true;
    final color = isDeath ? EnhancedTheme.errorRed : EnhancedTheme.successGreen;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(
                  isDeath
                      ? (cause.isEmpty ? 'Death' : 'Death · $cause')
                      : 'Birth',
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(text: kind, color: color),
            if (maternal) ...[
              const SizedBox(width: 6),
              const ReportBadge(text: 'maternal', color: EnhancedTheme.accentPurple),
            ],
            if (infant) ...[
              const SizedBox(width: 6),
              const ReportBadge(text: 'infant', color: EnhancedTheme.accentOrange),
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
          RegionEditChip(
            path: '/api/vital-events/${row['id']}/',
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
  String _kind = 'birth';
  bool _maternal = false;
  bool _infant = false;
  String _region = '';
  int? _causeId;
  List<Map<String, dynamic>> _diseases = [];
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;
  bool get _isDeath => _kind == 'death';

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      if (_kinds.contains(e['event_type'])) _kind = e['event_type'];
      _maternal = e['maternal_death'] == true;
      _infant = e['infant_death'] == true;
      _age.text = '${e['patient_age_group'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
      _causeId = e['cause'] as int?;
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
      // Birth carries no cause/death flags — clear them so an edited death→birth
      // doesn't leave stale mortality flags that would skew the ratios.
      final body = {
        'event_type': _kind,
        'cause': _isDeath ? _causeId : null,
        'maternal_death': _isDeath && _maternal,
        'infant_death': _isDeath && _infant,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/vital-events/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/vital-events/', body);
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
      title: _isEdit ? 'Edit vital event' : 'Record a vital event',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit event',
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _kind,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Event type'),
          items: [for (final k in _kinds) DropdownMenuItem(value: k, child: Text(k))],
          onChanged: (v) => setState(() => _kind = v!),
        ),
        if (_isDeath) ...[
          const SizedBox(height: 12),
          DropdownButtonFormField<int?>(
            initialValue: _causeId,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Cause of death (optional)'),
            items: [
              const DropdownMenuItem(value: null, child: Text('— unknown —')),
              for (final d in _diseases)
                DropdownMenuItem(value: d['id'] as int, child: Text('${d['name']}')),
            ],
            onChanged: (v) => setState(() => _causeId = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Maternal death'),
            subtitle: const Text('Related to pregnancy or childbirth'),
            value: _maternal,
            onChanged: (v) => setState(() => _maternal = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Infant death'),
            subtitle: const Text('Under 1 year of age'),
            value: _infant,
            onChanged: (v) => setState(() => _infant = v),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _age,
          decoration: const InputDecoration(labelText: 'Age group (e.g. 0-1, 25-34)'),
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
