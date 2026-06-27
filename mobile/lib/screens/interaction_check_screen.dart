import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../api.dart';
import '../l10n/app_localizations.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';

/// Interaction checker — "patient is on these N drugs, any conflicts?".
/// Pick 2+ medications, POST /api/interactions/check/, render every known
/// interaction among them. Tenant-scoped server-side.
class InteractionCheckScreen extends StatefulWidget {
  const InteractionCheckScreen({super.key});

  @override
  State<InteractionCheckScreen> createState() => _InteractionCheckScreenState();
}

class _InteractionCheckScreenState extends State<InteractionCheckScreen>
    with AutomaticKeepAliveClientMixin {
  List<Map<String, dynamic>> _meds = [];
  final _selected = <int>{};
  bool _loadingList = true;
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _result;

  @override
  bool get wantKeepAlive => true;

  static const _severityColor = {
    'minor': EnhancedTheme.primaryTeal,
    'moderate': Colors.orange,
    'major': EnhancedTheme.errorRed,
  };

  @override
  void initState() {
    super.initState();
    _loadMeds();
  }

  Future<void> _loadMeds() async {
    try {
      final rows = await api.getList('/api/medications/');
      setState(() => _meds = rows.cast<Map<String, dynamic>>());
    } catch (e) {
      setState(() => _error = e is ApiException ? e.friendly : e.toString());
    } finally {
      if (mounted) setState(() => _loadingList = false);
    }
  }

  Future<void> _run() async {
    if (_selected.length < 2) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await api.post('/api/interactions/check/',
          {'medication_ids': _selected.toList()});
      setState(() => _result = (r as Map).cast<String, dynamic>());
    } catch (e) {
      setState(() => _error = e is ApiException ? e.friendly : e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _medLabel(Map<String, dynamic> m) {
    final g = '${m['generic_name'] ?? ''}'.trim();
    return g.isNotEmpty ? g : '${m['brand_name'] ?? m['name'] ?? '#${m['id']}'}';
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final t = AppLocalizations.of(context);
    if (_loadingList) {
      return const Center(
          child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
    }
    if (_meds.isEmpty) {
      return EmptyState(
        icon: _error != null ? Icons.error_outline : Icons.medication_outlined,
        title: _error != null ? 'Something went wrong' : 'No medications',
        message: _error ?? 'No medications recorded to check.',
        color: _error != null ? EnhancedTheme.errorRed : EnhancedTheme.primaryTeal,
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(t.selectMedications,
            style: GoogleFonts.outfit(
              color: context.labelColor,
              fontWeight: FontWeight.w700,
              fontSize: 16,
            )),
        const SizedBox(height: 4),
        Text(t.selectMedicationsHint,
            style: TextStyle(color: context.hintColor, fontSize: 12)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final m in _meds)
              FilterChip(
                label: Text(_medLabel(m)),
                selected: _selected.contains(m['id']),
                onSelected: (on) => setState(() {
                  on ? _selected.add(m['id'] as int) : _selected.remove(m['id']);
                }),
              ),
          ],
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _busy || _selected.length < 2 ? null : _run,
          icon: const Icon(Icons.rule),
          label: Text(_busy ? '…' : t.checkInteractions(_selected.length)),
        ),
        const SizedBox(height: 16),
        if (_error != null && _result == null)
          EmptyState(
            icon: Icons.error_outline,
            title: 'Something went wrong',
            message: _error,
            color: EnhancedTheme.errorRed,
          ),
        if (_result != null) ..._results(context),
      ],
    );
  }

  List<Widget> _results(BuildContext context) {
    final rows = (_result!['interactions'] as List?) ?? [];
    final disclaimer = _result!['disclaimer'] as String?;
    if (rows.isEmpty) {
      return [
        const EmptyState(
          icon: Icons.check_circle_outline,
          title: 'No known interactions',
          message: 'No recorded conflicts among the selected medications.',
          color: EnhancedTheme.primaryTeal,
        ),
      ];
    }
    return [
      Text('Interactions found (${rows.length})',
          style: GoogleFonts.outfit(
            color: context.labelColor,
            fontWeight: FontWeight.w700,
            fontSize: 16,
          )),
      const SizedBox(height: 8),
      for (final row in rows.cast<Map<String, dynamic>>())
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _InteractionCard(row: row, severityColor: _severityColor),
        ),
      if (disclaimer != null) ...[
        const SizedBox(height: 8),
        Text(disclaimer,
            style: TextStyle(
                color: context.hintColor,
                fontSize: 11,
                fontStyle: FontStyle.italic)),
      ],
    ];
  }
}

/// Single interaction row — mirrors the card on the read-only Interactions list.
class _InteractionCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final Map<String, Color> severityColor;
  const _InteractionCard({required this.row, required this.severityColor});

  @override
  Widget build(BuildContext context) {
    final severity = '${row['severity'] ?? ''}';
    final color = severityColor[severity] ?? EnhancedTheme.primaryTeal;
    final desc = '${row['description'] ?? ''}'.trim();
    final rec = '${row['recommendation'] ?? ''}'.trim();
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
                  '${row['medication_a_name'] ?? row['medication_a']}'
                  '  ×  '
                  '${row['medication_b_name'] ?? row['medication_b']}',
                  style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  severity.isEmpty ? '—' : severity.toUpperCase(),
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.w700,
                    fontSize: 11,
                  ),
                ),
              ),
            ],
          ),
          if (desc.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(desc,
                style: TextStyle(
                    color: context.subLabelColor, height: 1.4, fontSize: 13)),
          ],
          if (rec.isNotEmpty) ...[
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.lightbulb_outline,
                    size: 16, color: EnhancedTheme.accentCyan),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(rec,
                      style: const TextStyle(
                        color: EnhancedTheme.accentCyan,
                        height: 1.4,
                        fontSize: 13,
                      )),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
