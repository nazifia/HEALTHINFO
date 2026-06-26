import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';

/// Collated adverse-drug-reaction stats.
/// Super-admins get the cross-tenant platform rollup (/api/analytics/platform/adr/),
/// which adds by_tenant / by_local / by_state; everyone else falls back to their
/// own tenant's ADR stats (/api/analytics/adr/).
class PlatformAdrScreen extends StatefulWidget {
  const PlatformAdrScreen({super.key});

  @override
  State<PlatformAdrScreen> createState() => _PlatformAdrScreenState();
}

class _PlatformAdrScreenState extends State<PlatformAdrScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    // Platform view is super-admin only; a 403/non-200 scopes down to tenant.
    try {
      final r = await api.get('/api/analytics/platform/adr/');
      return (r as Map).cast<String, dynamic>();
    } catch (_) {
      final r = await api.get('/api/analytics/adr/');
      return (r as Map).cast<String, dynamic>();
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
        setState(() => _future = f);
        await f;
      },
      child: FutureBuilder<Map<String, dynamic>>(
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
                title: 'Could not load ADR stats',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final d = snap.data!;
          final byTenant = (d['by_tenant'] as List?) ?? [];
          final byLocal = (d['by_local'] as List?) ?? [];
          final byState = (d['by_state'] as List?) ?? [];
          final trend = (d['trend'] as List?) ?? [];
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              GlassCard(
                padding: const EdgeInsets.all(20),
                child: Row(
                  children: [
                    const Icon(Icons.medication_liquid_outlined,
                        color: EnhancedTheme.primaryTeal, size: 28),
                    const SizedBox(width: 14),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${d['total'] ?? 0}',
                            style: GoogleFonts.outfit(
                              color: context.labelColor,
                              fontWeight: FontWeight.w800,
                              fontSize: 28,
                            )),
                        Text('Total reactions reported',
                            style: TextStyle(
                                color: context.hintColor, fontSize: 12)),
                      ],
                    ),
                  ],
                ),
              ),
              _TrendCard(rows: trend),
              _Breakdown(
                heading: 'By severity',
                icon: Icons.priority_high,
                rows: (d['by_severity'] as List?) ?? [],
                labelKey: 'severity',
              ),
              _Breakdown(
                heading: 'By outcome',
                icon: Icons.flag_outlined,
                rows: (d['by_outcome'] as List?) ?? [],
                labelKey: 'outcome',
              ),
              _Breakdown(
                heading: 'Top medications',
                icon: Icons.medication_outlined,
                rows: (d['top_medications'] as List?) ?? [],
                labelKey: 'medication__generic_name',
              ),
              _Breakdown(
                heading: 'Top reactions',
                icon: Icons.coronavirus_outlined,
                rows: (d['top_reactions'] as List?) ?? [],
                labelKey: 'reaction',
              ),
              if (byLocal.isNotEmpty)
                _Breakdown(
                  heading: 'By local area',
                  icon: Icons.location_city_outlined,
                  rows: byLocal,
                  labelKey: 'local',
                ),
              if (byState.isNotEmpty)
                _Breakdown(
                  heading: 'By state',
                  icon: Icons.map_outlined,
                  rows: byState,
                  labelKey: 'state',
                ),
              if (byTenant.isNotEmpty)
                _Breakdown(
                  heading: 'By tenant',
                  icon: Icons.apartment_outlined,
                  rows: byTenant,
                  labelKey: 'tenant__name',
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Reaction volume over the trailing 90 days (weekly buckets) from `trend`.
class _TrendCard extends StatelessWidget {
  final List<dynamic> rows;
  const _TrendCard({required this.rows});

  @override
  Widget build(BuildContext context) {
    final points = rows.cast<Map<String, dynamic>>();
    final total =
        points.fold<num>(0, (a, r) => a + ((r['count'] as num?) ?? 0));
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.show_chart,
                  color: EnhancedTheme.primaryTeal, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Reaction volume (90d)',
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    )),
              ),
              const SizedBox(width: 8),
              Text('$total total',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            ]),
            const SizedBox(height: 12),
            TrendLineChart(
              rows: [
                for (final r in points)
                  (
                    period: '${r['period'] ?? ''}',
                    value: (r['count'] as num?) ?? 0,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Breakdown extends StatelessWidget {
  final String heading;
  final IconData icon;
  final List<dynamic> rows;
  final String labelKey;
  const _Breakdown({
    required this.heading,
    required this.icon,
    required this.rows,
    required this.labelKey,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, color: EnhancedTheme.primaryTeal, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(heading,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    )),
              ),
            ]),
            const SizedBox(height: 10),
            MiniBarChart(
              rows: [
                for (final row in rows.cast<Map<String, dynamic>>())
                  (
                    label: '${row[labelKey] ?? ''}',
                    value: (row['count'] as num?) ?? 0,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
