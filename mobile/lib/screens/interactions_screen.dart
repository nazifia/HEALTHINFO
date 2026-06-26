import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';

/// Drug interactions — GET /api/interactions/.
/// Each row pairs two medications with a severity badge.
class InteractionsScreen extends StatefulWidget {
  const InteractionsScreen({super.key});

  @override
  State<InteractionsScreen> createState() => _InteractionsScreenState();
}

class _InteractionsScreenState extends State<InteractionsScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = api.getList('/api/interactions/');
  }

  static const _severityColor = {
    'minor': EnhancedTheme.primaryTeal,
    'moderate': Colors.orange,
    'major': EnhancedTheme.errorRed,
  };

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: () async {
        final f = api.getList('/api/interactions/');
        setState(() => _future = f);
        await f;
      },
      child: FutureBuilder<List<dynamic>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(
                child:
                    CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Something went wrong',
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
                icon: Icons.warning_amber_outlined,
                title: 'No interactions',
                message: 'No drug interactions recorded.',
              ),
            ]);
          }
          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            itemCount: items.length,
            separatorBuilder: (_, _) => const SizedBox(height: 10),
            itemBuilder: (context, i) {
              final row = items[i];
              final severity = '${row['severity'] ?? ''}';
              final color =
                  _severityColor[severity] ?? EnhancedTheme.primaryTeal;
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
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
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
                              color: context.subLabelColor,
                              height: 1.4,
                              fontSize: 13)),
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
            },
          );
        },
      ),
    );
  }
}
