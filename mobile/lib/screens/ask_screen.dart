import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../api.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/snack.dart';

/// AI assistant: asks /api/ai/ask/ (RAG). Shows the synthesised answer when an
/// API key is configured server-side, and always lists the retrieved sources —
/// so this one screen also covers semantic search.
class AskScreen extends StatefulWidget {
  const AskScreen({super.key});

  @override
  State<AskScreen> createState() => _AskScreenState();
}

class _AskScreenState extends State<AskScreen> {
  final _q = TextEditingController();
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _result;
  String? _vote; // 'up' / 'down' once the user rates the current answer

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  Future<void> _ask() async {
    final q = _q.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
      _vote = null; // fresh answer, clear previous rating
    });
    try {
      final r = await api.get('/api/ai/ask/', {'q': q});
      setState(() => _result = (r as Map).cast<String, dynamic>());
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _sendVote(String vote) async {
    final id = _result?['interaction_id'];
    if (id == null) return;
    setState(() => _vote = vote); // optimistic; feedback is best-effort
    try {
      await api.post('/api/analytics/ai/$id/feedback/', {'vote': vote});
    } catch (e) {
      if (mounted) {
        setState(() => _vote = null);
        showError(context, e is ApiException ? e.friendly : "Couldn't send feedback");
      }
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
                Icon(Icons.auto_awesome,
                    color: EnhancedTheme.primaryTeal.withValues(alpha: 0.8),
                    size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _q,
                    onSubmitted: (_) => _ask(),
                    textInputAction: TextInputAction.search,
                    decoration: const InputDecoration(
                      hintText: 'Ask a health question…',
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
                  onPressed: _busy ? null : _ask,
                ),
              ],
            ),
          ),
        ),
        Expanded(child: _body(context)),
      ],
    );
  }

  Widget _feedbackRow(BuildContext context) {
    final rated = _vote != null;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Row(
        children: [
          Text(
            rated ? 'Thanks for the feedback' : 'Was this helpful?',
            style: TextStyle(color: context.hintColor, fontSize: 12),
          ),
          const Spacer(),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: 'Helpful',
            icon: Icon(
              _vote == 'up' ? Icons.thumb_up : Icons.thumb_up_outlined,
              size: 18,
              color: _vote == 'up'
                  ? EnhancedTheme.primaryTeal
                  : context.hintColor,
            ),
            onPressed: rated ? null : () => _sendVote('up'),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            tooltip: 'Not helpful',
            icon: Icon(
              _vote == 'down' ? Icons.thumb_down : Icons.thumb_down_outlined,
              size: 18,
              color: _vote == 'down'
                  ? EnhancedTheme.errorRed
                  : context.hintColor,
            ),
            onPressed: rated ? null : () => _sendVote('down'),
          ),
        ],
      ),
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
    final result = _result;
    if (result == null) {
      return const EmptyState(
        icon: Icons.auto_awesome,
        title: 'Ask the health assistant',
        message: 'Answers come only from the health library, with sources.',
      );
    }

    final answer = result['answer'] as String?;
    final sources = (result['sources'] as List?) ?? [];
    final disclaimer = result['disclaimer'] as String?;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
      children: [
        GlassCard(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Answer',
                  style: GoogleFonts.outfit(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  )),
              const SizedBox(height: 8),
              Text(
                answer ??
                    'No generated answer (AI generation is off). '
                        'See the matching sources below.',
                style: TextStyle(
                    color: context.subLabelColor, height: 1.5, fontSize: 14),
              ),
              if (answer != null && result['interaction_id'] != null)
                _feedbackRow(context),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Text('Sources',
            style: GoogleFonts.outfit(
              color: context.labelColor,
              fontWeight: FontWeight.w700,
              fontSize: 16,
            )),
        const SizedBox(height: 8),
        if (sources.isEmpty)
          Text('No matching content.',
              style: TextStyle(color: context.hintColor, fontSize: 13))
        else
          for (final s in sources.cast<Map<String, dynamic>>())
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
                            color: EnhancedTheme.accentCyan
                                .withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            '${s['content_type']}',
                            style: const TextStyle(
                              color: EnhancedTheme.accentCyan,
                              fontWeight: FontWeight.w600,
                              fontSize: 11,
                            ),
                          ),
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
        if (disclaimer != null) ...[
          const SizedBox(height: 8),
          Text(disclaimer,
              style: TextStyle(
                  color: context.hintColor,
                  fontSize: 11,
                  fontStyle: FontStyle.italic)),
        ],
      ],
    );
  }
}
