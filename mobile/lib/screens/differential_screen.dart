import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../api.dart';
import '../l10n/app_localizations.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';

/// Differential diagnosis — pick symptoms, POST /api/differential/, get diseases
/// ranked by how many of the chosen symptoms they match. Decision-support only;
/// the backend disclaimer is shown verbatim.
class DifferentialScreen extends StatefulWidget {
  const DifferentialScreen({super.key});

  @override
  State<DifferentialScreen> createState() => _DifferentialScreenState();
}

class _DifferentialScreenState extends State<DifferentialScreen>
    with AutomaticKeepAliveClientMixin {
  List<Map<String, dynamic>> _symptoms = [];
  final _selected = <int>{};
  bool _loadingList = true;
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _result;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _loadSymptoms();
  }

  Future<void> _loadSymptoms() async {
    try {
      final rows = await api.getList('/api/symptoms/');
      setState(() => _symptoms = rows.cast<Map<String, dynamic>>());
    } catch (e) {
      setState(() => _error = e is ApiException ? e.friendly : e.toString());
    } finally {
      if (mounted) setState(() => _loadingList = false);
    }
  }

  Future<void> _run() async {
    if (_selected.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await api.post('/api/differential/',
          {'symptom_ids': _selected.toList()});
      setState(() => _result = (r as Map).cast<String, dynamic>());
    } catch (e) {
      setState(() => _error = e is ApiException ? e.friendly : e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final t = AppLocalizations.of(context);
    if (_loadingList) {
      return const Center(
          child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
    }
    if (_symptoms.isEmpty) {
      return EmptyState(
        icon: _error != null ? Icons.error_outline : Icons.healing_outlined,
        title: _error != null ? 'Something went wrong' : 'No symptoms',
        message: _error ?? 'No symptoms recorded to choose from.',
        color: _error != null ? EnhancedTheme.errorRed : EnhancedTheme.primaryTeal,
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Text(t.selectSymptoms,
            style: GoogleFonts.outfit(
              color: context.labelColor,
              fontWeight: FontWeight.w700,
              fontSize: 16,
            )),
        const SizedBox(height: 4),
        Text(t.selectSymptomsHint,
            style: TextStyle(color: context.hintColor, fontSize: 12)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final s in _symptoms)
              FilterChip(
                label: Text('${s['name']}'),
                selected: _selected.contains(s['id']),
                onSelected: (on) => setState(() {
                  on ? _selected.add(s['id'] as int) : _selected.remove(s['id']);
                }),
              ),
          ],
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _busy || _selected.isEmpty ? null : _run,
          icon: const Icon(Icons.search),
          label: Text(_busy ? '…' : t.findDiseases(_selected.length)),
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
    final rows = (_result!['results'] as List?) ?? [];
    final disclaimer = _result!['disclaimer'] as String?;
    if (rows.isEmpty) {
      return [
        const EmptyState(
          icon: Icons.search_off_outlined,
          title: 'No matches',
          message: 'No published disease matches the chosen symptoms.',
        ),
      ];
    }
    final top = (rows.first as Map)['matched'] as int? ?? 1;
    return [
      Text('Possible conditions',
          style: GoogleFonts.outfit(
            color: context.labelColor,
            fontWeight: FontWeight.w700,
            fontSize: 16,
          )),
      const SizedBox(height: 8),
      for (final row in rows.cast<Map<String, dynamic>>())
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: GlassCard(
            borderRadius: 16,
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${row['name']}',
                          style: TextStyle(
                            color: context.labelColor,
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          )),
                      if ('${row['icd10_code'] ?? ''}'.trim().isNotEmpty)
                        Text('ICD-10: ${row['icd10_code']}',
                            style: TextStyle(
                                color: context.hintColor, fontSize: 12)),
                    ],
                  ),
                ),
                _MatchBadge(matched: row['matched'] as int? ?? 0, top: top),
              ],
            ),
          ),
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

class _MatchBadge extends StatelessWidget {
  final int matched;
  final int top;
  const _MatchBadge({required this.matched, required this.top});

  @override
  Widget build(BuildContext context) {
    // Shade by strength relative to the strongest match in this result set.
    final strong = top > 0 && matched >= top;
    final color = strong ? EnhancedTheme.primaryTeal : EnhancedTheme.accentCyan;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text('$matched match${matched == 1 ? '' : 'es'}',
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w700,
            fontSize: 12,
          )),
    );
  }
}
