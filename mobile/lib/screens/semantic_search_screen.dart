import 'package:flutter/material.dart';

import '../main.dart';
import '../api.dart';
import '../l10n/app_localizations.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';

/// Semantic search — embedding nearest-neighbour over the tenant's published
/// content. GET /api/ai/semantic-search/?q=. Like "Ask AI" but retrieval only:
/// no generated answer, more raw matches, works with no model key configured.
class SemanticSearchScreen extends StatefulWidget {
  const SemanticSearchScreen({super.key});

  @override
  State<SemanticSearchScreen> createState() => _SemanticSearchScreenState();
}

class _SemanticSearchScreenState extends State<SemanticSearchScreen> {
  final _q = TextEditingController();
  bool _busy = false;
  String? _error;
  List<Map<String, dynamic>>? _results;

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final q = _q.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await api.get('/api/ai/semantic-search/', {'q': q});
      final rows = ((r as Map)['results'] as List?) ?? [];
      setState(() => _results = rows.cast<Map<String, dynamic>>());
    } catch (e) {
      setState(() => _error = e is ApiException ? e.friendly : e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: GlassCard(
            borderRadius: 16,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                const SizedBox(width: 8),
                Icon(Icons.travel_explore,
                    color: EnhancedTheme.primaryTeal.withValues(alpha: 0.8),
                    size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _q,
                    onSubmitted: (_) => _search(),
                    textInputAction: TextInputAction.search,
                    decoration: InputDecoration(
                      hintText: AppLocalizations.of(context).semanticSearchHint,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      filled: false,
                      contentPadding: EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send_rounded,
                      color: EnhancedTheme.primaryTeal),
                  onPressed: _busy ? null : _search,
                ),
              ],
            ),
          ),
        ),
        Expanded(child: _body(context)),
      ],
    );
  }

  Widget _body(BuildContext context) {
    if (_busy) {
      return const Center(
          child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
    }
    if (_error != null) {
      return EmptyState(
        icon: Icons.error_outline,
        title: 'Something went wrong',
        message: _error,
        color: EnhancedTheme.errorRed,
      );
    }
    final results = _results;
    if (results == null) {
      return const EmptyState(
        icon: Icons.travel_explore,
        title: 'Semantic search',
        message: 'Finds related content by meaning, not just keywords.',
      );
    }
    if (results.isEmpty) {
      return const EmptyState(
        icon: Icons.search_off_outlined,
        title: 'No matches',
        message: 'Nothing in the library matched that query.',
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
      children: [
        for (final s in results)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: GlassCard(
              borderRadius: 16,
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color:
                              EnhancedTheme.accentCyan.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text('${s['content_type']}',
                            style: const TextStyle(
                              color: EnhancedTheme.accentCyan,
                              fontWeight: FontWeight.w600,
                              fontSize: 11,
                            )),
                      ),
                      const Spacer(),
                      Text('score ${s['score']}',
                          style: TextStyle(
                              color: context.hintColor, fontSize: 11)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text('${s['text']}',
                      style: TextStyle(
                          color: context.subLabelColor,
                          height: 1.4,
                          fontSize: 13)),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
