import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';

/// Secondary analytics dashboards in one scroll: conversion funnel, AI answer
/// quality, peer benchmark, weekly retention, and adverse-reaction signal.
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
    final r = await Future.wait([
      _one('/api/analytics/funnel/'),
      _one('/api/analytics/ai-quality/'),
      _one('/api/analytics/benchmark/'),
      _one('/api/analytics/retention/'),
      _one('/api/analytics/adr/'),
    ]);
    Map<String, dynamic>? m(int i) => (r[i] as Map?)?.cast<String, dynamic>();
    return _Bundle(
      funnel: m(0),
      aiQuality: m(1),
      benchmark: m(2),
      retention: (r[3] as List?) ?? const [],
      adr: m(4),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
        setState(() => _future = f);
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
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              const StatsHeader(
                icon: Icons.query_stats,
                title: 'Analytics',
                subtitle: 'Funnel, AI quality, benchmarks & signals',
                color: EnhancedTheme.accentPurple,
              ),
              if (b.funnel != null) _FunnelCard(d: b.funnel!),
              if (b.aiQuality != null) _AiQualityCard(d: b.aiQuality!),
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
  final Map<String, dynamic>? aiQuality;
  final Map<String, dynamic>? benchmark;
  final List<dynamic> retention;
  final Map<String, dynamic>? adr;
  _Bundle({
    required this.funnel,
    required this.aiQuality,
    required this.benchmark,
    required this.retention,
    required this.adr,
  });
}

class _FunnelCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const _FunnelCard({required this.d});

  @override
  Widget build(BuildContext context) {
    return StatSection(
      icon: Icons.filter_alt_outlined,
      heading: 'Conversion funnel',
      color: EnhancedTheme.primaryTeal,
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

class _AiQualityCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const _AiQualityCard({required this.d});

  @override
  Widget build(BuildContext context) {
    final fb = (d['feedback'] as Map?)?.cast<String, dynamic>() ?? const {};
    final downvoted = (d['top_downvoted'] as List?) ?? [];
    final up = (fb['up'] as num?)?.toInt() ?? 0;
    final down = (fb['down'] as num?)?.toInt() ?? 0;
    return StatSection(
      icon: Icons.auto_awesome_outlined,
      heading: 'AI answer quality',
      color: EnhancedTheme.accentPurple,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              DonutChart(
                value: down,
                total: up + down,
                color: EnhancedTheme.errorRed,
                centerLabel: pctOf(d['downvote_rate'] as num?),
                centerSub: 'downvoted',
                size: 104,
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    StatMetric('answered', '${d['answered'] ?? 0}'),
                    const SizedBox(height: 8),
                    StatMetric('retrieval only', '${d['retrieval_only'] ?? 0}'),
                    const SizedBox(height: 8),
                    Text('▲ $up   ▼ $down   ·   ${d['unrated'] ?? 0} unrated',
                        style:
                            TextStyle(color: context.hintColor, fontSize: 12)),
                  ],
                ),
              ),
            ],
          ),
          if (downvoted.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text('Most-downvoted questions',
                style: TextStyle(
                    color: context.subLabelColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            MiniBarChart(rows: [
              for (final r in downvoted.cast<Map<String, dynamic>>())
                (
                  label: '${r['question'] ?? '—'}',
                  value: (r['count'] as num?) ?? 0
                ),
            ]),
          ],
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
    return StatSection(
      icon: Icons.leaderboard_outlined,
      heading: 'Peer benchmark (case reports)',
      color: EnhancedTheme.accentOrange,
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
    return StatSection(
      icon: Icons.show_chart,
      heading: 'Weekly active users',
      color: EnhancedTheme.accentCyan,
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
    return StatSection(
      icon: Icons.medication_liquid_outlined,
      heading: 'Adverse reactions (${d['total'] ?? 0} total)',
      color: EnhancedTheme.errorRed,
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
