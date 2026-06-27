import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';

/// Platform-wide super-admin dashboard — GET /api/analytics/platform/.
/// Cross-tenant rollup: tenant/user counts, search volume, per-tenant breakdown,
/// AI satisfaction, ADR collation. Read-only. Gated to super_admin in the nav.
class SuperAdminDashboardScreen extends StatefulWidget {
  const SuperAdminDashboardScreen({super.key});

  @override
  State<SuperAdminDashboardScreen> createState() =>
      _SuperAdminDashboardScreenState();
}

class _SuperAdminDashboardScreenState extends State<SuperAdminDashboardScreen> {
  late Future<Map<String, dynamic>> _future;
  DateTimeRange? _range;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  String _d(DateTime t) =>
      '${t.year.toString().padLeft(4, '0')}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';

  Future<Map<String, dynamic>> _load() async {
    final q = _range == null
        ? ''
        : '?from=${_d(_range!.start)}&to=${_d(_range!.end)}';
    final r = await api.get('/api/analytics/platform/$q');
    return (r as Map).cast<String, dynamic>();
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 5),
      lastDate: now,
      initialDateRange: _range,
    );
    if (picked == null) return;
    setState(() {
      _range = picked;
      _future = _load();
    });
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
            return const SkeletonCards(cards: 4, statRow: true);
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Could not load platform dashboard',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final d = snap.data!;
          final trend =
              ((d['search_trend'] as List?) ?? []).cast<Map<String, dynamic>>();
          final byTenant = ((d['searches_by_tenant'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          final fb = (d['ai_feedback'] as Map?)?.cast<String, dynamic>() ?? const {};
          final up = (fb['up'] as num?)?.toInt() ?? 0;
          final down = (fb['down'] as num?)?.toInt() ?? 0;
          final satTotal = up + down;
          final satPct = satTotal == 0 ? null : (up / satTotal * 100).round();
          final adr = (d['adverse_reactions'] as Map?)?.cast<String, dynamic>() ?? const {};
          final searchTotal =
              trend.fold<num>(0, (a, r) => a + ((r['count'] as num?) ?? 0));
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              DashTitleBar(
                title: 'Platform Control',
                accent: EnhancedTheme.accentPurple,
                subtitle: _range == null
                    ? 'All tenants · all time'
                    : '${_d(_range!.start)} → ${_d(_range!.end)}',
                trailing: IconButton(
                  onPressed: _pickRange,
                  icon: const Icon(Icons.date_range),
                  color: EnhancedTheme.accentPurple,
                  tooltip: 'Date range',
                ),
              ),
              KpiStrip(tiles: [
                KpiChip(
                  icon: Icons.apartment_outlined,
                  label: 'Tenants',
                  value: '${d['total_tenants'] ?? 0}',
                  color: EnhancedTheme.accentPurple,
                ),
                KpiChip(
                  icon: Icons.group_outlined,
                  label: 'Total Users',
                  value: '${d['total_users'] ?? 0}',
                  color: EnhancedTheme.primaryTeal,
                ),
                KpiChip(
                  icon: Icons.search,
                  label: 'Searches',
                  value: '${d['total_searches'] ?? 0}',
                  color: EnhancedTheme.accentCyan,
                ),
                KpiChip(
                  icon: Icons.medication_liquid_outlined,
                  label: 'Adverse Reactions',
                  value: '${adr['total'] ?? 0}',
                  color: EnhancedTheme.errorRed,
                ),
                KpiChip(
                  icon: Icons.thumb_up_alt_outlined,
                  label: 'AI Positive',
                  value: satPct == null ? '—' : '$satPct%',
                  color: EnhancedTheme.successGreen,
                ),
                KpiChip(
                  icon: Icons.show_chart,
                  label: 'Search Vol 90d',
                  value: '$searchTotal',
                  color: EnhancedTheme.accentOrange,
                ),
              ]),
              const SizedBox(height: 14),
              PanelCard(
                title: 'Search Volume (90d, weekly)',
                accent: EnhancedTheme.accentPurple,
                trailing: Text('$searchTotal total',
                    style: TextStyle(color: context.hintColor, fontSize: 12)),
                child: _Trend(points: trend),
              ),
              PanelCard(
                title: 'Searches by Tenant',
                accent: EnhancedTheme.primaryTeal,
                child: ComparisonBars(
                  rows: [
                    for (final r in byTenant.take(12))
                      (
                        label: '${r['tenant__name'] ?? '—'}',
                        value: (r['count'] as num?) ?? 0,
                        color: EnhancedTheme.primaryTeal,
                      ),
                  ],
                ),
              ),
              PanelCard(
                title: 'AI Answer Satisfaction',
                accent: EnhancedTheme.successGreen,
                child: Row(
                  children: [
                    DonutChart(
                      value: up,
                      total: satTotal,
                      color: EnhancedTheme.successGreen,
                      centerLabel: satPct == null ? '—' : '$satPct%',
                      centerSub: 'positive',
                      size: 110,
                    ),
                    const SizedBox(width: 20),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          StatMetric('thumbs up', '$up',
                              color: EnhancedTheme.successGreen),
                          const SizedBox(height: 10),
                          StatMetric('thumbs down', '$down',
                              color: EnhancedTheme.errorRed),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              PanelCard(
                title: 'Adverse Reactions by Tenant',
                accent: EnhancedTheme.errorRed,
                child: ComparisonBars(
                  rows: [
                    for (final r in ((adr['by_tenant'] as List?) ?? [])
                        .cast<Map<String, dynamic>>()
                        .take(12))
                      (
                        label: '${r['tenant__name'] ?? '—'}',
                        value: (r['count'] as num?) ?? 0,
                        color: EnhancedTheme.errorRed,
                      ),
                  ],
                ),
              ),
              PanelCard(
                title: 'Content Gaps (no results)',
                accent: EnhancedTheme.accentOrange,
                child: ComparisonBars(
                  rows: [
                    for (final r in ((d['content_gaps'] as List?) ?? [])
                        .cast<Map<String, dynamic>>()
                        .take(10))
                      (
                        label: '${r['query'] ?? '—'}',
                        value: (r['count'] as num?) ?? 0,
                        color: EnhancedTheme.accentOrange,
                      ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// 90-day weekly search volume line. rows: [{period: iso-date, count: n}].
class _Trend extends StatelessWidget {
  final List<Map<String, dynamic>> points;
  const _Trend({required this.points});

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) {
      return Text('No data yet.',
          style: TextStyle(color: context.hintColor, fontSize: 13));
    }
    final spots = [
      for (var i = 0; i < points.length; i++)
        FlSpot(i.toDouble(), ((points[i]['count'] as num?) ?? 0).toDouble()),
    ];
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    return SizedBox(
      height: 160,
      child: LineChart(LineChartData(
        minY: 0,
        maxY: (maxY <= 0 ? 1 : maxY) * 1.2,
        gridData: const FlGridData(show: false),
        borderData: FlBorderData(show: false),
        titlesData: const FlTitlesData(show: false),
        lineTouchData: const LineTouchData(enabled: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: EnhancedTheme.accentPurple,
            barWidth: 2.5,
            dotData: FlDotData(show: spots.length == 1),
            belowBarData: BarAreaData(
              show: true,
              color: EnhancedTheme.accentPurple.withValues(alpha: 0.12),
            ),
          ),
        ],
      )),
    );
  }
}
