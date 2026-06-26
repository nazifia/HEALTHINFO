import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/snack.dart';

/// Case reports — GET/POST /api/case-reports/.
/// Staff list their tenant's reports and file new ones via the FAB. Reports
/// collate centrally (super-admin platform view) for analysis.
class CasesScreen extends StatefulWidget {
  const CasesScreen({super.key});

  @override
  State<CasesScreen> createState() => _CasesScreenState();
}

const _severity = ['mild', 'moderate', 'severe', 'critical'];
const _outcome = ['ongoing', 'recovered', 'referred', 'deceased'];

const _severityColor = {
  'mild': EnhancedTheme.primaryTeal,
  'moderate': Colors.orange,
  'severe': Colors.deepOrange,
  'critical': EnhancedTheme.errorRed,
};

class _CasesScreenState extends State<CasesScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = api.getList('/api/case-reports/');
  }

  void _reload() {
    setState(() => _future = api.getList('/api/case-reports/'));
  }

  Future<void> _openForm([Map<String, dynamic>? existing]) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ReportForm(existing: existing),
    );
    if (saved == true) {
      _reload();
      if (mounted) {
        showSuccess(context, existing == null ? 'Case report filed.' : 'Case updated.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openForm,
        backgroundColor: EnhancedTheme.primaryTeal,
        icon: const Icon(Icons.add, color: Colors.white),
        label: const Text('Report case',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          _reload();
          await _future;
        },
        child: FutureBuilder<List<dynamic>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(
                  child: CircularProgressIndicator(
                      color: EnhancedTheme.primaryTeal));
            }
            if (snap.hasError) {
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: Icons.error_outline,
                  title: 'Could not load cases',
                  message: '${snap.error}',
                  color: EnhancedTheme.errorRed,
                ),
              ]);
            }
            final items = (snap.data ?? []).cast<Map<String, dynamic>>();
            if (items.isEmpty) {
              return ListView(children: const [
                SizedBox(height: 80),
                EmptyState(
                  icon: Icons.assignment_outlined,
                  title: 'No cases yet',
                  message: 'Tap "Report case" to file the first one.',
                ),
              ]);
            }
            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
              itemCount: items.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) => _CaseCard(
                row: items[i],
                onChanged: _reload,
                onEdit: () => _openForm(items[i]),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _CaseCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback onChanged;
  final VoidCallback onEdit;
  const _CaseCard({required this.row, required this.onChanged, required this.onEdit});

  @override
  Widget build(BuildContext context) {
    final severity = '${row['severity'] ?? ''}';
    final color = _severityColor[severity] ?? EnhancedTheme.primaryTeal;
    final notes = '${row['notes'] ?? ''}'.trim();
    final reporter = '${row['reporter_name'] ?? ''}'.trim();
    final age = '${row['patient_age_group'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  row['disease'] == null ? 'Unspecified condition' : 'Case #${row['id']}',
                  style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _Badge(text: severity, color: color),
              const SizedBox(width: 6),
              _Badge(
                text: '${row['outcome'] ?? ''}',
                color: EnhancedTheme.accentCyan,
              ),
              // Edit only for report-capable roles; backend re-checks.
              FutureBuilder<String?>(
                future: api.myRole(),
                builder: (context, snap) => api.roleCanReport(snap.data)
                    ? IconButton(
                        visualDensity: VisualDensity.compact,
                        icon: Icon(Icons.edit_outlined,
                            size: 18, color: context.hintColor),
                        onPressed: onEdit,
                      )
                    : const SizedBox.shrink(),
              ),
            ],
          ),
          if (notes.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(notes,
                style: TextStyle(
                    color: context.subLabelColor, height: 1.4, fontSize: 13)),
          ],
          const SizedBox(height: 8),
          Text(
            [if (age.isNotEmpty) 'Age $age', if (reporter.isNotEmpty) 'by $reporter']
                .join('  ·  '),
            style: TextStyle(color: context.hintColor, fontSize: 11),
          ),
          const SizedBox(height: 8),
          RegionEditChip(
            path: '/api/case-reports/${row['id']}/',
            current: '${row['region'] ?? ''}'.trim(),
            onSaved: onChanged,
          ),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String text;
  final Color color;
  const _Badge({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        text.isEmpty ? '—' : text.toUpperCase(),
        style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 11),
      ),
    );
  }
}

/// Case form in a bottom sheet. Pops `true` after a successful POST (new) or
/// PATCH (when [existing] is supplied).
class _ReportForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _ReportForm({this.existing});

  @override
  State<_ReportForm> createState() => _ReportFormState();
}

class _ReportFormState extends State<_ReportForm> {
  final _notes = TextEditingController();
  final _age = TextEditingController();
  String _sev = 'mild';
  String _out = 'ongoing';
  String _region = '';
  int? _diseaseId;
  List<Map<String, dynamic>> _diseases = [];
  List<Map<String, dynamic>> _symptoms = [];
  List<Map<String, dynamic>> _medications = [];
  final Set<int> _symptomIds = {};
  final Set<int> _medicationIds = {};
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _notes.text = '${e['notes'] ?? ''}';
      _age.text = '${e['patient_age_group'] ?? ''}';
      if (_severity.contains(e['severity'])) _sev = e['severity'];
      if (_outcome.contains(e['outcome'])) _out = e['outcome'];
      _region = '${e['region'] ?? ''}';
      _diseaseId = e['disease'] as int?;
      _symptomIds.addAll((e['symptoms'] as List? ?? []).cast<int>());
      _medicationIds.addAll((e['medications'] as List? ?? []).cast<int>());
    }
    _load('/api/diseases/', (r) => _diseases = r);
    _load('/api/symptoms/', (r) => _symptoms = r);
    _load('/api/medications/', (r) => _medications = r);
  }

  Future<void> _load(
      String path, void Function(List<Map<String, dynamic>>) assign) async {
    try {
      final rows = await api.getList(path);
      setState(() => assign(rows.cast<Map<String, dynamic>>()));
    } catch (_) {
      // All links are optional on a report; an empty list just hides the picker.
    }
  }

  @override
  void dispose() {
    _notes.dispose();
    _age.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'disease': _diseaseId,
        'severity': _sev,
        'outcome': _out,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
        'symptoms': _symptomIds.toList(),
        'medications': _medicationIds.toList(),
      };
      if (_isEdit) {
        await api.patch('/api/case-reports/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/case-reports/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '$e');
      showError(context, '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: inset),
      child: Container(
        decoration: BoxDecoration(
          color: context.scaffoldBg,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: context.hintColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Text(_isEdit ? 'Edit case' : 'Report a case',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
              const SizedBox(height: 16),
              DropdownButtonFormField<int?>(
                initialValue: _diseaseId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Disease (optional)'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('— none —')),
                  for (final d in _diseases)
                    DropdownMenuItem(
                        value: d['id'] as int, child: Text('${d['name']}')),
                ],
                onChanged: (v) => setState(() => _diseaseId = v),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: _sev,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Severity'),
                      items: [
                        for (final s in _severity)
                          DropdownMenuItem(value: s, child: Text(s)),
                      ],
                      onChanged: (v) => setState(() => _sev = v!),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: _out,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Outcome'),
                      items: [
                        for (final o in _outcome)
                          DropdownMenuItem(value: o, child: Text(o)),
                      ],
                      onChanged: (v) => setState(() => _out = v!),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _age,
                decoration: const InputDecoration(
                    labelText: 'Patient age group (e.g. 0-5, 60+)'),
              ),
              const SizedBox(height: 12),
              RegionPicker(
                  initial: _region.isEmpty ? null : _region,
                  onChanged: (r) => _region = r),
              const SizedBox(height: 12),
              TextField(
                controller: _notes,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Notes'),
              ),
              _ChipPicker(
                heading: 'Symptoms',
                rows: _symptoms,
                labelField: 'name',
                selected: _symptomIds,
                onToggle: (id) => setState(() => _symptomIds.toggle(id)),
              ),
              _ChipPicker(
                heading: 'Medications',
                rows: _medications,
                labelField: 'generic_name',
                selected: _medicationIds,
                onToggle: (id) => setState(() => _medicationIds.toggle(id)),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!,
                    style: const TextStyle(
                        color: EnhancedTheme.errorRed, fontSize: 13)),
              ],
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _saving ? null : _submit,
                  style: FilledButton.styleFrom(
                      backgroundColor: EnhancedTheme.primaryTeal),
                  child: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : Text(_isEdit ? 'Save changes' : 'Submit report'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

extension _ToggleSet on Set<int> {
  void toggle(int id) => contains(id) ? remove(id) : add(id);
}

/// Multi-select chip list backed by a shared selected-id set. Hides itself
/// when there's nothing to pick.
class _ChipPicker extends StatelessWidget {
  final String heading;
  final String labelField;
  final List<Map<String, dynamic>> rows;
  final Set<int> selected;
  final void Function(int id) onToggle;
  const _ChipPicker({
    required this.heading,
    required this.labelField,
    required this.rows,
    required this.selected,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 16),
        Text(heading,
            style: TextStyle(
                color: context.subLabelColor,
                fontSize: 13,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            for (final r in rows)
              FilterChip(
                label: Text('${r[labelField]}'),
                selected: selected.contains(r['id']),
                selectedColor:
                    EnhancedTheme.primaryTeal.withValues(alpha: 0.2),
                onSelected: (_) => onToggle(r['id'] as int),
              ),
          ],
        ),
      ],
    );
  }
}
