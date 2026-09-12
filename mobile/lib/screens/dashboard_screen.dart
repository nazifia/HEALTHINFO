import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/stats_rows.dart';

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

  /// Diagnosis the prescribing panel is drilled into, or null for all of them.
  String? _diagnosis;

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
    // The role rides on the payload so the panels below can narrow to it.
    final role = (await api.me())?['role']?.toString();
    return {...(r as Map).cast<String, dynamic>(), '_role': role};
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
        setState(() { _future = f; });
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
          final searchTotal =
              trend.fold<num>(0, (a, r) => a + ((r['count'] as num?) ?? 0));
          final diagnoses = (d['top_diagnoses'] as List?) ?? [];
          // Each profession reads its own half: the engagement numbers are
          // the administrator's, the prescribing panels every clinician's
          // and the pharmacist's.
          final role = d['_role'] as String?;
          final engagement = readsPanel(role, 'engagement');
          final prescribing = readsPanel(role, 'prescribing');
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              DashTitleBar(
                title: 'Health Analytics',
                subtitle: _range == null
                    ? 'All time'
                    : '${_d(_range!.start)} → ${_d(_range!.end)}',
                trailing: IconButton(
                  onPressed: _pickRange,
                  icon: const Icon(Icons.date_range),
                  color: EnhancedTheme.accentCyan,
                  tooltip: 'Date range',
                ),
              ),
              if (engagement) KpiStrip(tiles: [
                KpiChip(
                  icon: Icons.group_outlined,
                  label: 'Active Users 30d',
                  value: '${d['active_users'] ?? 0}',
                  color: EnhancedTheme.accentPurple,
                ),
                KpiChip(
                  icon: Icons.show_chart,
                  label: 'Search Volume',
                  value: '$searchTotal',
                  color: EnhancedTheme.accentCyan,
                ),
              ]),
              const SizedBox(height: 14),
              _RankList(
                heading: 'Popular diseases',
                color: EnhancedTheme.accentPurple,
                rows: (d['popular_diseases'] as List?) ?? [],
                titleKey: 'name',
                countKey: 'views',
              ),
              _RankList(
                heading: 'Popular medications',
                color: EnhancedTheme.accentOrange,
                rows: (d['popular_medications'] as List?) ?? [],
                titleKey: 'name',
                countKey: 'views',
              ),
              // The clinical half of the dashboard: what was treated, and what
              // was written for it. Each label carries its dispensed count,
              // because a bar counts orders written, not orders handed over.
              if (prescribing) _RankList(
                heading: 'Top diagnoses (prescribing)',
                color: EnhancedTheme.accentCyan,
                rows: diagnosisRows(diagnoses),
                titleKey: 'diagnosis',
                countKey: 'count',
                // Tap a bar to drill the panel below into that diagnosis;
                // tapping the same bar again goes back to all of them.
                onTap: (i) => setState(() {
                  final name = '${(diagnoses[i] as Map)['diagnosis']}';
                  _diagnosis = _diagnosis == name ? null : name;
                }),
              ),
              if (prescribing) _RankList(
                heading: _diagnosis == null
                    ? 'Prescribed for each diagnosis'
                    : 'Prescribed for $_diagnosis',
                color: EnhancedTheme.successGreen,
                rows: diagnosisPairRows(
                    pairsFor(d['by_diagnosis_medication'], _diagnosis)),
                titleKey: 'pair',
                countKey: 'count',
                trailing: _diagnosis == null
                    ? null
                    : TextButton(
                        onPressed: () => setState(() => _diagnosis = null),
                        child: const Text('Show all'),
                      ),
              ),
              if (engagement) _RankList(
                heading: 'Content gaps (no results)',
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

class _RankList extends StatelessWidget {
  final String heading;
  final Color color;
  final List<dynamic> rows;
  final String titleKey;
  final String countKey;
  final void Function(int index)? onTap;
  final Widget? trailing;
  const _RankList({
    required this.heading,
    required this.color,
    required this.rows,
    required this.titleKey,
    required this.countKey,
    this.onTap,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return PanelCard(
      title: heading,
      accent: color,
      trailing: trailing,
      child: MiniBarChart(
        onTap: onTap,
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
