import 'package:flutter/material.dart';

import '../main.dart';
import '../nigeria.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/snack.dart';

/// Adverse drug reactions — GET/POST /api/adverse-reactions/.
/// Pharmacovigilance: staff file a suspected harm from a medication. Reports
/// collate centrally (super-admin ADR analytics) for signal detection.
class AdrScreen extends StatefulWidget {
  const AdrScreen({super.key});

  @override
  State<AdrScreen> createState() => _AdrScreenState();
}

const _severity = ['mild', 'moderate', 'severe', 'life_threatening'];
const _outcome = ['ongoing', 'recovered', 'recovered_with_sequelae', 'fatal'];

const _severityColor = {
  'mild': EnhancedTheme.primaryTeal,
  'moderate': Colors.orange,
  'severe': Colors.deepOrange,
  'life_threatening': EnhancedTheme.errorRed,
};

class _AdrScreenState extends State<AdrScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = api.getList('/api/adverse-reactions/');
  }

  void _reload() {
    setState(() => _future = api.getList('/api/adverse-reactions/'));
  }

  Future<void> _openForm([Map<String, dynamic>? existing]) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AdrForm(existing: existing),
    );
    if (saved == true) {
      _reload();
      if (mounted) {
        showSuccess(context, existing == null ? 'Reaction reported.' : 'Reaction updated.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'fab_adr',
        onPressed: _openForm,
        backgroundColor: EnhancedTheme.primaryTeal,
        icon: const Icon(Icons.add, color: Colors.white),
        label: const Text('Report reaction',
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
                  title: 'Could not load reactions',
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
                  icon: Icons.medication_liquid_outlined,
                  title: 'No reactions yet',
                  message: 'Tap "Report reaction" to file the first one.',
                ),
              ]);
            }
            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
              itemCount: items.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) => _AdrCard(
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

class _AdrCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback onChanged;
  final VoidCallback onEdit;
  const _AdrCard({required this.row, required this.onChanged, required this.onEdit});

  @override
  Widget build(BuildContext context) {
    final severity = '${row['severity'] ?? ''}';
    final color = _severityColor[severity] ?? EnhancedTheme.primaryTeal;
    final reaction = '${row['reaction'] ?? ''}'.trim();
    final med = '${row['medication_name'] ?? ''}'.trim();
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
                  reaction.isEmpty ? 'ADR #${row['id']}' : reaction,
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
          if (med.isNotEmpty) ...[
            const SizedBox(height: 6),
            Row(children: [
              const Icon(Icons.medication_outlined,
                  size: 14, color: EnhancedTheme.accentOrange),
              const SizedBox(width: 6),
              Expanded(
                child: Text(med,
                    style: TextStyle(
                        color: context.subLabelColor,
                        fontWeight: FontWeight.w600,
                        fontSize: 13)),
              ),
            ]),
          ],
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
            path: '/api/adverse-reactions/${row['id']}/',
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
        text.isEmpty ? '—' : text.replaceAll('_', ' ').toUpperCase(),
        style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 11),
      ),
    );
  }
}

/// ADR form in a bottom sheet. Pops `true` after a successful POST (new) or
/// PATCH (when [existing] is supplied). Medication + reaction text are required.
class _AdrForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _AdrForm({this.existing});

  @override
  State<_AdrForm> createState() => _AdrFormState();
}

class _AdrFormState extends State<_AdrForm> {
  final _reaction = TextEditingController();
  final _notes = TextEditingController();
  final _age = TextEditingController();
  String _sev = 'mild';
  String _out = 'ongoing';
  String _region = '';
  int? _medicationId;
  List<Map<String, dynamic>> _medications = [];
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _reaction.text = '${e['reaction'] ?? ''}';
      _notes.text = '${e['notes'] ?? ''}';
      _age.text = '${e['patient_age_group'] ?? ''}';
      if (_severity.contains(e['severity'])) _sev = e['severity'];
      if (_outcome.contains(e['outcome'])) _out = e['outcome'];
      _region = '${e['region'] ?? ''}';
      _medicationId = e['medication'] as int?;
    }
    _loadMeds();
  }

  Future<void> _loadMeds() async {
    try {
      final rows = await api.getList('/api/medications/');
      setState(() => _medications = rows.cast<Map<String, dynamic>>());
    } catch (_) {
      // Leave the picker empty; submit guard below blocks a medication-less POST.
    }
  }

  @override
  void dispose() {
    _reaction.dispose();
    _notes.dispose();
    _age.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_medicationId == null || _reaction.text.trim().isEmpty) {
      setState(() => _error = 'Pick a medication and describe the reaction.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'medication': _medicationId,
        'reaction': _reaction.text.trim(),
        'severity': _sev,
        'outcome': _out,
        'patient_age_group': _age.text.trim(),
        'region': _region,
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/adverse-reactions/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/adverse-reactions/', body);
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
              Text(_isEdit ? 'Edit reaction' : 'Report a reaction',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
              const SizedBox(height: 16),
              DropdownButtonFormField<int?>(
                initialValue: _medicationId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Medication'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('— select —')),
                  for (final m in _medications)
                    DropdownMenuItem(
                        value: m['id'] as int,
                        child: Text('${m['generic_name']}')),
                ],
                onChanged: (v) => setState(() => _medicationId = v),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _reaction,
                decoration: const InputDecoration(
                    labelText: 'Reaction (e.g. rash, anaphylaxis)'),
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
                          DropdownMenuItem(
                              value: s, child: Text(s.replaceAll('_', ' '))),
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
                          DropdownMenuItem(
                              value: o, child: Text(o.replaceAll('_', ' '))),
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
