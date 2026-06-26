import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';

/// Where reports come from. Pools both report streams (case reports + adverse
/// drug reactions) and shows their origin: reporter, region, tenant.
/// Super-admins get the cross-tenant view (/api/analytics/platform/sources/);
/// everyone else falls back to their own tenant's sources (/api/analytics/sources/).
class ReportSourcesScreen extends StatefulWidget {
  const ReportSourcesScreen({super.key});

  @override
  State<ReportSourcesScreen> createState() => _ReportSourcesScreenState();
}

class _ReportSourcesScreenState extends State<ReportSourcesScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    // Platform view is super-admin only; a 403/non-200 means scope down to tenant.
    try {
      final r = await api.get('/api/analytics/platform/sources/');
      return (r as Map).cast<String, dynamic>();
    } catch (_) {
      final r = await api.get('/api/analytics/sources/');
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
                title: 'Could not load report sources',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final d = snap.data!;
          final byTenant = (d['by_tenant'] as List?) ?? [];
          final byRegion = (d['by_region'] as List?) ?? [];
          final byReporter = (d['by_reporter'] as List?) ?? [];
          final cases = (d['total_cases'] as num?) ?? 0;
          final adrs = (d['total_adrs'] as num?) ?? 0;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              GlassCard(
                padding: const EdgeInsets.all(20),
                child: Row(
                  children: [
                    const Icon(Icons.inventory_2_outlined,
                        color: EnhancedTheme.primaryTeal, size: 28),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${cases + adrs}',
                              style: GoogleFonts.outfit(
                                color: context.labelColor,
                                fontWeight: FontWeight.w800,
                                fontSize: 28,
                              )),
                          Text('Reports from all sources',
                              style: TextStyle(
                                  color: context.hintColor, fontSize: 12)),
                          const SizedBox(height: 2),
                          Text('$cases case reports  ·  $adrs adverse reactions',
                              style: TextStyle(
                                  color: context.hintColor, fontSize: 11)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              if (byReporter.isNotEmpty)
                _Breakdown(
                  heading: 'By reporter',
                  icon: Icons.person_outline,
                  rows: byReporter,
                  labelKey: 'reporter__username',
                ),
              if (byRegion.isNotEmpty)
                _Breakdown(
                  heading: 'By region',
                  icon: Icons.public_outlined,
                  rows: byRegion,
                  labelKey: 'region',
                ),
              if (byTenant.isNotEmpty)
                _Breakdown(
                  heading: 'By tenant',
                  icon: Icons.apartment_outlined,
                  rows: byTenant,
                  labelKey: 'tenant__name',
                ),
              if (byReporter.isEmpty && byRegion.isEmpty && byTenant.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(top: 60),
                  child: EmptyState(
                    icon: Icons.inbox_outlined,
                    title: 'No reports yet',
                    message: 'Filed case reports and adverse reactions show '
                        'their sources here.',
                  ),
                ),
            ],
          );
        },
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
