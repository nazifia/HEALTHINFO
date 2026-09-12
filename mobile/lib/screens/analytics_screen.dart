import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/stats_rows.dart';

/// Secondary analytics dashboards in one scroll: conversion funnel, peer
/// benchmark, daily retention, and adverse-reaction signal.
/// Each card fetches its own endpoint and degrades independently — one failing
/// call never blanks the whole screen.
class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  late Future<_Bundle> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  /// Fetch one endpoint, swallowing errors to a null so a 403/offline call
  /// just hides its card instead of failing the page.
  Future<dynamic> _one(String path) async {
    try {
      return await api.get(path);
    } catch (_) {
      return null;
    }
  }

  Future<_Bundle> _load() async {
    // Only the panels this profession reads are fetched; a null hides its
    // card and its KPI chip exactly as a failed call would.
    final role = (await api.me())?['role']?.toString();
    Future<dynamic> want(String panel, String path) =>
        readsPanel(role, panel) ? _one(path) : Future.value(null);
    final r = await Future.wait([
      want('engagement', '/api/analytics/funnel/'),
      want('engagement', '/api/analytics/benchmark/'),
      want('engagement', '/api/analytics/retention/'),
      want('adr', '/api/analytics/adr/'),
      want('consultations', '/api/analytics/consultations/'),
    ]);
    Map<String, dynamic>? m(int i) => (r[i] as Map?)?.cast<String, dynamic>();
    return _Bundle(
      funnel: m(0),
      benchmark: m(1),
      retention: (r[2] as List?) ?? const [],
      adr: m(3),
      consultations: m(4),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
        setState(() { _future = f; });
        await f;
      },
      child: FutureBuilder<_Bundle>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const SkeletonCards(cards: 4, statRow: false);
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Could not load analytics',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final b = snap.data!;
          num? bn(Map<String, dynamic>? m, String k) => m?[k] as num?;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              const DashTitleBar(
                title: 'Analytics',
                subtitle: 'Funnel, benchmarks & signals',
                accent: EnhancedTheme.accentPurple,
              ),
              KpiStrip(tiles: [
                if (b.funnel != null) ...[
                  KpiChip(
                    icon: Icons.search,
                    label: 'Searches',
                    value: '${bn(b.funnel, 'searches') ?? 0}',
                    color: EnhancedTheme.primaryTeal,
                  ),
                  KpiChip(
                    icon: Icons.visibility_outlined,
                    label: 'Views',
                    value: '${bn(b.funnel, 'views') ?? 0}',
                    color: EnhancedTheme.accentCyan,
                  ),
                  KpiChip(
                    icon: Icons.assignment_outlined,
                    label: 'Case Reports',
                    value: '${bn(b.funnel, 'case_reports') ?? 0}',
                    color: EnhancedTheme.accentPurple,
                  ),
                ],
                if (b.adr != null)
                  KpiChip(
                    icon: Icons.medication_liquid_outlined,
                    label: 'Adverse Rxns',
                    value: '${bn(b.adr, 'total') ?? 0}',
                    color: EnhancedTheme.accentOrange,
                  ),
                if (b.consultations != null)
                  KpiChip(
                    icon: Icons.pending_actions_outlined,
                    label: 'Open Visits',
                    value: '${bn(b.consultations, 'open') ?? 0}',
                    color: EnhancedTheme.infoBlue,
                  ),
              ]),
              const SizedBox(height: 14),
              if (b.consultations != null)
                _ConsultationStatsCard(d: b.consultations!),
              if (b.funnel != null) _FunnelCard(d: b.funnel!),
              if (b.benchmark != null) _BenchmarkCard(d: b.benchmark!),
              if (b.retention.isNotEmpty) _RetentionCard(rows: b.retention),
              if (b.adr != null) _AdrStatsCard(d: b.adr!),
            ],
          );
        },
      ),
    );
  }
}

class _Bundle {
  final Map<String, dynamic>? funnel;
  final Map<String, dynamic>? benchmark;
  final List<dynamic> retention;
  final Map<String, dynamic>? adr;
  final Map<String, dynamic>? consultations;
  _Bundle({
    required this.funnel,
    required this.benchmark,
    required this.retention,
    required this.adr,
    required this.consultations,
  });
}

class _FunnelCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const _FunnelCard({required this.d});

  @override
  Widget build(BuildContext context) {
    return PanelCard(
      title: 'Conversion Funnel',
      accent: EnhancedTheme.primaryTeal,
      child: Column(
        children: [
          MiniBarChart(rows: [
            (label: 'Search', value: (d['searches'] as num?) ?? 0),
            (label: 'View', value: (d['views'] as num?) ?? 0),
            (label: 'Case', value: (d['case_reports'] as num?) ?? 0),
          ]),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              Expanded(
                  child: StatMetric(
                      'views / search', pctOf(d['view_per_search'] as num?))),
              Expanded(
                  child: StatMetric(
                      'cases / view', pctOf(d['case_per_view'] as num?))),
            ],
          ),
        ],
      ),
    );
  }
}

class _BenchmarkCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const _BenchmarkCard({required this.d});

  @override
  Widget build(BuildContext context) {
    num n(String k) => (d[k] as num?) ?? 0;
    return PanelCard(
      title: 'Peer Benchmark (case reports)',
      accent: EnhancedTheme.accentOrange,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ComparisonBars(rows: [
            (label: 'You', value: n('your_case_reports'), color: EnhancedTheme.accentOrange),
            (label: 'Network median', value: n('platform_median'), color: EnhancedTheme.primaryTeal),
            (label: 'Network max', value: n('platform_max'), color: EnhancedTheme.accentPurple),
          ]),
          Text('Compared across ${d['tenants_compared'] ?? 0} tenants',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
        ],
      ),
    );
  }
}

class _RetentionCard extends StatelessWidget {
  final List<dynamic> rows;
  const _RetentionCard({required this.rows});

  @override
  Widget build(BuildContext context) {
    final points = rows.cast<Map<String, dynamic>>();
    return PanelCard(
      title: 'Daily Active Users',
      accent: EnhancedTheme.accentCyan,
      child: TrendLineChart(
        color: EnhancedTheme.accentCyan,
        rows: [
          for (final r in points)
            (
              period: '${r['period'] ?? ''}',
              value: (r['active_users'] as num?) ?? 0
            ),
        ],
      ),
    );
  }
}

class _AdrStatsCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const _AdrStatsCard({required this.d});

  @override
  Widget build(BuildContext context) {
    final topMeds = (d['top_medications'] as List?) ?? [];
    final topReactions = (d['top_reactions'] as List?) ?? [];
    return PanelCard(
      title: 'Adverse Reactions (${d['total'] ?? 0} total)',
      accent: EnhancedTheme.errorRed,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (topMeds.isNotEmpty) ...[
            Text('Top medications',
                style: TextStyle(
                    color: context.subLabelColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            MiniBarChart(rows: [
              for (final r in topMeds.cast<Map<String, dynamic>>())
                (
                  label: '${r['medication__generic_name'] ?? '—'}',
                  value: (r['count'] as num?) ?? 0
                ),
            ]),
            const SizedBox(height: 12),
          ],
          if (topReactions.isNotEmpty) ...[
            Text('Top reactions',
                style: TextStyle(
                    color: context.subLabelColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            MiniBarChart(rows: [
              for (final r in topReactions.cast<Map<String, dynamic>>())
                (
                  label: '${r['reaction'] ?? '—'}',
                  value: (r['count'] as num?) ?? 0
                ),
            ]),
          ],
        ],
      ),
    );
  }
}

/// Clinic load — /api/analytics/consultations/. What patients came with, how
/// long a visit takes, and where they went next.
class _ConsultationStatsCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const _ConsultationStatsCard({required this.d});

  /// A `_grouped` list from the API as chart rows. [field] is the column it
  /// was grouped by, which is the key each row carries its label under.
  static List<({String label, num value})> _rows(Object? raw, String field,
      {int limit = 6}) {
    final rows = (raw as List?)?.cast<Map<String, dynamic>>() ?? const [];
    return [
      for (final r in rows.take(limit))
        (
          label: '${r[field] ?? ''}'.trim().isEmpty
              ? 'Unspecified'
              : '${r[field]}'.replaceAll('_', ' '),
          value: (r['count'] as num?) ?? 0,
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final minutes = d['median_minutes_to_close'] as num?;
    final byDisposition = _rows(d['by_disposition'], 'disposition');
    final complaints = _rows(d['top_complaints'], 'chief_complaint');
    final trend = (d['trend'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
    return PanelCard(
      title: 'Consultations (${d['total'] ?? 0} total)',
      accent: EnhancedTheme.primaryTeal,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(child: StatMetric('open', '${d['open'] ?? 0}')),
            Expanded(
                child: StatMetric(
                    'admitted', pctOf(d['admission_rate'] as num?))),
            Expanded(
                child: StatMetric('median visit',
                    minutes == null ? '—' : '$minutes min')),
          ]),
          if (byDisposition.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text('Where they went next',
                style: TextStyle(
                    color: context.subLabelColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            MiniBarChart(rows: byDisposition),
          ],
          if (complaints.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text('Top complaints',
                style: TextStyle(
                    color: context.subLabelColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            MiniBarChart(rows: complaints),
          ],
          if (trend.isNotEmpty) ...[
            const SizedBox(height: 12),
            TrendLineChart(
              color: EnhancedTheme.primaryTeal,
              rows: [
                for (final r in trend)
                  (
                    period: '${r['period'] ?? ''}',
                    value: (r['count'] as num?) ?? 0
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
