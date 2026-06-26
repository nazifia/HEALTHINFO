import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';

/// Outbreak surveillance — disease clusters whose latest week spikes above their
/// trailing baseline. Super-admins get the cross-tenant view
/// (/api/analytics/platform/surveillance/); everyone else their own tenant's
/// (/api/analytics/surveillance/). Response: {"alerts": [...]}.
class SurveillanceScreen extends StatefulWidget {
  const SurveillanceScreen({super.key});

  @override
  State<SurveillanceScreen> createState() => _SurveillanceScreenState();
}

class _SurveillanceScreenState extends State<SurveillanceScreen> {
  late Future<List<dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<dynamic>> _load() async {
    // Platform view is super-admin only; a 403/non-200 scopes down to tenant.
    Map data;
    try {
      data = await api.get('/api/analytics/platform/surveillance/') as Map;
    } catch (_) {
      data = await api.get('/api/analytics/surveillance/') as Map;
    }
    return (data['alerts'] as List?) ?? [];
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
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
                title: 'Could not load surveillance',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final alerts = (snap.data ?? []).cast<Map<String, dynamic>>();
          if (alerts.isEmpty) {
            return ListView(children: const [
              SizedBox(height: 80),
              EmptyState(
                icon: Icons.verified_outlined,
                title: 'No outbreak signals',
                message: 'No disease is spiking above its baseline right now.',
                color: EnhancedTheme.successGreen,
              ),
            ]);
          }
          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            itemCount: alerts.length,
            separatorBuilder: (_, _) => const SizedBox(height: 12),
            itemBuilder: (context, i) => _AlertCard(alert: alerts[i]),
          );
        },
      ),
    );
  }
}

class _AlertCard extends StatelessWidget {
  final Map<String, dynamic> alert;
  const _AlertCard({required this.alert});

  @override
  Widget build(BuildContext context) {
    final name = '${alert['name'] ?? 'Unknown'}';
    final code = '${alert['icd10_code'] ?? ''}'.trim();
    final current = (alert['current_week'] as num?) ?? 0;
    final baseline = (alert['baseline_mean'] as num?) ?? 0;
    final weeks = (alert['weekly_counts'] as List?)?.cast<num>() ?? const [];
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.notifications_active_outlined,
                  color: EnhancedTheme.errorRed, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(name,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    )),
              ),
              if (code.isNotEmpty)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: EnhancedTheme.accentPurple.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(code,
                      style: const TextStyle(
                          color: EnhancedTheme.accentPurple,
                          fontWeight: FontWeight.w700,
                          fontSize: 11)),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Text('$current',
                  style: GoogleFonts.outfit(
                    color: EnhancedTheme.errorRed,
                    fontWeight: FontWeight.w800,
                    fontSize: 26,
                  )),
              const SizedBox(width: 6),
              Flexible(
                child: Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('cases this week',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: context.hintColor, fontSize: 12)),
                ),
              ),
              const Spacer(),
              Flexible(
                child: Text('baseline ~$baseline/wk',
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: context.hintColor, fontSize: 12)),
              ),
            ],
          ),
          if (weeks.isNotEmpty) ...[
            const SizedBox(height: 12),
            TrendLineChart(
              color: EnhancedTheme.errorRed,
              rows: [
                for (var i = 0; i < weeks.length; i++)
                  (period: 'w$i', value: weeks[i]),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
