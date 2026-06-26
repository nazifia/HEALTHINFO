import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';

/// Collated case reports rollup.
/// Super-admins get the cross-tenant platform view (/api/analytics/platform/cases/);
/// everyone else falls back to their own tenant's rollup (/api/analytics/cases/).
class CollatedReportsScreen extends StatefulWidget {
  const CollatedReportsScreen({super.key});

  @override
  State<CollatedReportsScreen> createState() => _CollatedReportsScreenState();
}

class _CollatedReportsScreenState extends State<CollatedReportsScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    // Platform view is super-admin only; a 403/non-200 means scope down to tenant.
    try {
      final r = await api.get('/api/analytics/platform/cases/');
      return (r as Map).cast<String, dynamic>();
    } catch (_) {
      final r = await api.get('/api/analytics/cases/');
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
                title: 'Could not load reports',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final d = snap.data!;
          final byTenant = (d['by_tenant'] as List?) ?? [];
          final byRegion = (d['by_region'] as List?) ?? [];
          final byRegionState = (d['by_region_state'] as List?) ?? [];
          final byIcd10 = (d['by_icd10'] as List?) ?? [];
          final byLocal = (d['by_local'] as List?) ?? [];
          final byState = (d['by_state'] as List?) ?? [];
          final byNational = (d['by_national'] as List?) ?? [];
          final trend = (d['case_trend'] as List?) ?? [];
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              GlassCard(
                padding: const EdgeInsets.all(20),
                child: Row(
                  children: [
                    const Icon(Icons.assignment_turned_in_outlined,
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
                        Text('Total cases reported',
                            style: TextStyle(
                                color: context.hintColor, fontSize: 12)),
                        // IDSR severity signal: deaths and case-fatality rate.
                        Text(
                            '${d['deaths'] ?? 0} deaths · CFR ${_cfr(d['case_fatality_rate'])}',
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
                heading: 'By age group',
                icon: Icons.cake_outlined,
                rows: (d['by_age_group'] as List?) ?? [],
                labelKey: 'patient_age_group',
              ),
              _Breakdown(
                heading: 'Top diseases',
                icon: Icons.coronavirus_outlined,
                rows: (d['top_diseases'] as List?) ?? [],
                labelKey: 'disease__name',
              ),
              if (byRegionState.isNotEmpty)
                _Breakdown(
                  heading: 'By state',
                  icon: Icons.map_outlined,
                  rows: byRegionState,
                  labelKey: 'state',
                ),
              if (byRegion.isNotEmpty)
                _Breakdown(
                  heading: 'By region (LGA)',
                  icon: Icons.public_outlined,
                  rows: byRegion,
                  labelKey: 'region',
                ),
              if (byIcd10.isNotEmpty)
                _Breakdown(
                  heading: 'By ICD-10 code',
                  icon: Icons.qr_code_2_outlined,
                  rows: byIcd10,
                  labelKey: 'icd10_code',
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
              if (byNational.isNotEmpty)
                _Breakdown(
                  heading: 'By national',
                  icon: Icons.account_balance_outlined,
                  rows: byNational,
                  labelKey: 'national',
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

/// Case-fatality rate as a percent string. Backend sends a 0..1 fraction or null.
String _cfr(dynamic rate) =>
    rate is num ? '${(rate * 100).toStringAsFixed(1)}%' : '—';

/// Case volume over the trailing 90 days (weekly buckets) from `case_trend`.
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
                child: Text('Case volume (90d)',
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
