import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/export_csv.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Notifiable cases — GET /api/reports/notifiable/.
///
/// The regulator pull: every case of a legally-notifiable disease in the
/// window, exactly as it must be sent on. Read-only — a case is filed on the
/// case-report screen, and this one only selects what the law asks for.
///
/// The endpoint answers {"count": N, "cases": [...]} rather than a DRF page,
/// so it loads here directly instead of through ReportListScreen.
class NotifiableScreen extends StatefulWidget {
  const NotifiableScreen({super.key});

  @override
  State<NotifiableScreen> createState() => _NotifiableScreenState();
}

class _NotifiableScreenState extends State<NotifiableScreen> {
  int _days = 30;
  late Future<List<Map<String, dynamic>>> _future = _load();

  static const _windows = {
    7: 'Last 7 days',
    30: 'Last 30 days',
    90: 'Last quarter',
    365: 'Last year',
  };

  // The window as the API takes it, shared by the list and the CSV export so
  // the file is never a different period from the rows above it.
  Map<String, String> get _query => {
        'from': DateTime.now()
            .subtract(Duration(days: _days))
            .toIso8601String()
            .split('T')
            .first,
      };

  Future<List<Map<String, dynamic>>> _load() async {
    final data = await api.get('/api/reports/notifiable/', _query) as Map;
    return ((data['cases'] as List?) ?? []).cast<Map<String, dynamic>>();
  }

  void _reload() => setState(() { _future = _load(); });

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        _reload();
        await _future;
      },
      child: FutureBuilder<List<Map<String, dynamic>>>(
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
                title: 'Could not load notifiable cases',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final rows = snap.data ?? const <Map<String, dynamic>>[];
          final deaths = rows.where((r) => r['outcome'] == 'deceased').length;
          final diseases =
              rows.map((r) => '${r['disease__name']}').toSet().length;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              DashTitleBar(
                title: 'Notifiable cases',
                subtitle: 'What must be reported onward to public health',
                trailing: CsvExportButton(
                  path: '/api/reports/notifiable/',
                  filename: 'notifiable_cases_${_days}d.csv',
                  query: _query,
                ),
              ),
              const SizedBox(height: 8),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  for (final w in _windows.entries) ...[
                    ChoiceChip(
                      label: Text(w.value),
                      selected: _days == w.key,
                      onSelected: (_) {
                        setState(() => _days = w.key);
                        _reload();
                      },
                    ),
                    const SizedBox(width: 8),
                  ],
                ]),
              ),
              const SizedBox(height: 12),
              KpiRow(tiles: [
                KpiTile(
                    icon: Icons.flag_outlined,
                    label: 'Cases',
                    value: '${rows.length}',
                    color: EnhancedTheme.accentOrange),
                KpiTile(
                    icon: Icons.coronavirus_outlined,
                    label: 'Diseases',
                    value: '$diseases',
                    color: EnhancedTheme.primaryTeal),
                KpiTile(
                    icon: Icons.dangerous_outlined,
                    label: 'Deaths',
                    value: '$deaths',
                    color: EnhancedTheme.errorRed),
              ]),
              const SizedBox(height: 12),
              if (rows.isEmpty)
                const EmptyState(
                  icon: Icons.verified_outlined,
                  title: 'Nothing notifiable',
                  message: 'No notifiable disease was reported in this window.',
                  color: EnhancedTheme.successGreen,
                ),
              for (final row in rows)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _CaseCard(row: row),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _CaseCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _CaseCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final code = '${row['disease__icd10_code'] ?? ''}'.trim();
    final who = [
      '${row['patient_age_group'] ?? ''}',
      '${row['patient_sex'] ?? ''}',
      '${row['region'] ?? ''}',
    ].where((s) => s.trim().isNotEmpty).join(' · ');
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['disease__name'] ?? '—'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['outcome'] ?? 'unknown'}',
              color: statusColor(row['outcome'])),
        ]),
        const SizedBox(height: 4),
        Text(
            '${'${row['created_at']}'.split('T').first}'
            ' · ${row['severity'] ?? '—'}'
            '${code.isEmpty ? '' : ' · $code'}'
            '${who.isEmpty ? '' : ' · $who'}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
      ]),
    );
  }
}
