import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';

/// Tenant analytics dashboard — GET /api/analytics/tenant/.
/// Read-only summary cards + ranked lists.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
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
    final r = await api.get('/api/analytics/tenant/$q');
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
                title: 'Could not load dashboard',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final d = snap.data!;
          final trend = ((d['search_trend'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          final spark = [
            for (final r in trend) (r['count'] as num?) ?? 0,
          ];
          final fb = (d['ai_feedback'] as Map?)?.cast<String, dynamic>() ?? const {};
          final up = (fb['up'] as num?)?.toInt() ?? 0;
          final down = (fb['down'] as num?)?.toInt() ?? 0;
          final satTotal = up + down;
          final satPct = satTotal == 0 ? null : (up / satTotal * 100).round();
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              StatsHeader(
                icon: Icons.insights,
                title: 'Dashboard',
                subtitle: _range == null
                    ? 'All time'
                    : '${_d(_range!.start)} → ${_d(_range!.end)}',
                trailing: IconButton(
                  onPressed: _pickRange,
                  icon: const Icon(Icons.date_range),
                  color: EnhancedTheme.primaryTeal,
                  tooltip: 'Date range',
                ),
              ),
              KpiRow(tiles: [
                KpiTile(
                  icon: Icons.search,
                  label: 'Searches',
                  value: '${d['total_searches'] ?? 0}',
                  color: EnhancedTheme.primaryTeal,
                  spark: spark.isEmpty ? null : spark,
                ),
                KpiTile(
                  icon: Icons.group_outlined,
                  label: 'Active users (30d)',
                  value: '${d['active_users'] ?? 0}',
                  color: EnhancedTheme.accentPurple,
                ),
              ]),
              const SizedBox(height: 12),
              StatSection(
                icon: Icons.show_chart,
                heading: 'Search volume (30d)',
                trailing: Text(
                    '${trend.fold<num>(0, (a, r) => a + ((r['count'] as num?) ?? 0))} total',
                    style: TextStyle(color: context.hintColor, fontSize: 12)),
                child: _SearchTrend(points: trend),
              ),
              StatSection(
                icon: Icons.thumb_up_alt_outlined,
                heading: 'AI answer satisfaction',
                color: EnhancedTheme.successGreen,
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
              _RankList(
                heading: 'Top searches',
                icon: Icons.trending_up,
                color: EnhancedTheme.primaryTeal,
                rows: (d['top_searches'] as List?) ?? [],
                titleKey: 'query',
                countKey: 'count',
              ),
              _RankList(
                heading: 'Popular diseases',
                icon: Icons.coronavirus_outlined,
                color: EnhancedTheme.accentPurple,
                rows: (d['popular_diseases'] as List?) ?? [],
                titleKey: 'name',
                countKey: 'views',
              ),
              _RankList(
                heading: 'Popular medications',
                icon: Icons.medication_outlined,
                color: EnhancedTheme.accentOrange,
                rows: (d['popular_medications'] as List?) ?? [],
                titleKey: 'name',
                countKey: 'views',
              ),
              _RankList(
                heading: 'Content gaps (no results)',
                icon: Icons.search_off_outlined,
                color: EnhancedTheme.errorRed,
                rows: (d['content_gaps'] as List?) ?? [],
                titleKey: 'query',
                countKey: 'count',
              ),
            ],
          );
        },
      ),
    );
  }
}

/// 30-day search volume line chart. rows: [{period: iso-date, count: n}].
class _SearchTrend extends StatelessWidget {
  final List<Map<String, dynamic>> points;
  const _SearchTrend({required this.points});

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) {
      return Text('No data yet.',
          style: TextStyle(color: context.hintColor, fontSize: 13));
    }
    return SizedBox(height: 160, child: LineChart(_chartData(points)));
  }

  LineChartData _chartData(List<Map<String, dynamic>> points) {
    final spots = [
      for (var i = 0; i < points.length; i++)
        FlSpot(i.toDouble(), ((points[i]['count'] as num?) ?? 0).toDouble()),
    ];
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    return LineChartData(
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
          color: EnhancedTheme.primaryTeal,
          barWidth: 2.5,
          // A single point draws no line segment; show the dot so it's visible.
          dotData: FlDotData(show: spots.length == 1),
          belowBarData: BarAreaData(
            show: true,
            color: EnhancedTheme.primaryTeal.withValues(alpha: 0.12),
          ),
        ),
      ],
    );
  }
}

class _RankList extends StatelessWidget {
  final String heading;
  final IconData icon;
  final Color color;
  final List<dynamic> rows;
  final String titleKey;
  final String countKey;
  const _RankList({
    required this.heading,
    required this.icon,
    required this.color,
    required this.rows,
    required this.titleKey,
    required this.countKey,
  });

  @override
  Widget build(BuildContext context) {
    return StatSection(
      icon: icon,
      heading: heading,
      color: color,
      child: MiniBarChart(
        rows: [
          for (final row in rows.cast<Map<String, dynamic>>())
            (
              label: '${row[titleKey] ?? '—'}',
              value: (row[countKey] as num?) ?? 0,
            ),
        ],
      ),
    );
  }
}
