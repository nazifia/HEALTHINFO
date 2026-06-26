import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Appointments / telemedicine — GET/POST /api/appointments/.
/// Feeds utilization (in-person vs telemedicine) and the no-show rate.
class AppointmentsScreen extends StatelessWidget {
  const AppointmentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/appointments/',
      fabLabel: 'Add appointment',
      emptyIcon: Icons.event_outlined,
      emptyTitle: 'No appointments yet',
      emptyMessage: 'Tap "Add appointment" to schedule one.',
      savedMessage: 'Appointment saved.',
      card: (row, reload, edit) => _Card(row: row, reload: reload, edit: edit),
      form: (existing) => _Form(existing: existing),
    );
  }
}

const _modes = ['in_person', 'telemedicine'];
const _statuses = ['scheduled', 'completed', 'no_show', 'cancelled'];

const _statusColor = {
  'scheduled': EnhancedTheme.infoBlue,
  'completed': EnhancedTheme.successGreen,
  'no_show': EnhancedTheme.errorRed,
  'cancelled': Colors.grey,
};

class _Card extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final VoidCallback edit;
  const _Card({required this.row, required this.reload, required this.edit});

  @override
  Widget build(BuildContext context) {
    final mode = '${row['mode'] ?? ''}';
    final status = '${row['status'] ?? ''}';
    final reason = '${row['reason'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(reason.isEmpty ? 'Appointment #${row['id']}' : reason,
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            const SizedBox(width: 8),
            ReportBadge(
                text: mode == 'telemedicine' ? 'tele' : 'in-person',
                color: EnhancedTheme.accentCyan),
            const SizedBox(width: 6),
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
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/appointments/${row['id']}/',
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
  final _reason = TextEditingController();
  final _notes = TextEditingController();
  String _mode = 'in_person';
  String _status = 'scheduled';
  String _region = '';
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      if (_modes.contains(e['mode'])) _mode = e['mode'];
      if (_statuses.contains(e['status'])) _status = e['status'];
      _reason.text = '${e['reason'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _region = '${e['region'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _reason.dispose();
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
        'mode': _mode,
        'status': _status,
        'reason': _reason.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/appointments/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/appointments/', body);
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
      title: _isEdit ? 'Edit appointment' : 'New appointment',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Submit',
      onSubmit: _submit,
      children: [
        Row(children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: _mode,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Mode'),
              items: [
                for (final m in _modes)
                  DropdownMenuItem(value: m, child: Text(m.replaceAll('_', ' '))),
              ],
              onChanged: (v) => setState(() => _mode = v!),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: _status,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Status'),
              items: [
                for (final s in _statuses)
                  DropdownMenuItem(value: s, child: Text(s.replaceAll('_', ' '))),
              ],
              onChanged: (v) => setState(() => _status = v!),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _reason,
          decoration: const InputDecoration(labelText: 'Reason'),
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
