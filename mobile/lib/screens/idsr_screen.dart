import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/export_csv.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'report_scaffold.dart';

/// IDSR weekly epidemiological summary — GET /api/analytics/idsr/.
///
/// Super-admins get the central NCDC collation (/api/analytics/platform/idsr/);
/// everyone else their own facility's return. Response: {"weeks": N,
/// "summary": [{epi_week, disease, icd10_code, notifiable, cases, deaths,
/// case_fatality_rate}, ...]} newest week first.
///
/// Rows are grouped by epi-week here only for reading — the server already
/// ordered them, so grouping never reorders, it just inserts the headings.
/// The CSV the public-health authority expects is the same ?format=csv the web
/// client downloads — here it goes out through the platform share sheet.
class IdsrScreen extends StatefulWidget {
  const IdsrScreen({super.key});

  @override
  State<IdsrScreen> createState() => _IdsrScreenState();
}

class _IdsrScreenState extends State<IdsrScreen> {
  int _weeks = 8;
  // Which endpoint answered, so the CSV export pulls the same scope as the
  // rows on screen rather than guessing at the reader's role a second time.
  String _path = '/api/analytics/idsr/';
  late Future<List<Map<String, dynamic>>> _future = _load();

  static const _windows = {4: '4 weeks', 8: '8 weeks', 13: '1 quarter', 26: '6 months'};

  Future<List<Map<String, dynamic>>> _load() async {
    final q = {'weeks': '$_weeks'};
    Map data;
    // Platform view is super-admin only; a 403 scopes down to this tenant.
    try {
      data = await api.get('/api/analytics/platform/idsr/', q) as Map;
      _path = '/api/analytics/platform/idsr/';
    } catch (_) {
      data = await api.get('/api/analytics/idsr/', q) as Map;
      _path = '/api/analytics/idsr/';
    }
    return ((data['summary'] as List?) ?? []).cast<Map<String, dynamic>>();
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
                child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Could not load the IDSR return',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final rows = snap.data ?? const <Map<String, dynamic>>[];
          final cases = rows.fold<num>(0, (t, r) => t + ((r['cases'] as num?) ?? 0));
          final deaths = rows.fold<num>(0, (t, r) => t + ((r['deaths'] as num?) ?? 0));
          final notifiable = rows.where((r) => r['notifiable'] == true).length;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              DashTitleBar(
                title: 'IDSR weekly summary',
                subtitle: 'Cases, deaths and case-fatality by epi-week',
                trailing: CsvExportButton(
                  path: _path,
                  filename: 'idsr_${_weeks}w.csv',
                  query: {'weeks': '$_weeks'},
                ),
              ),
              const SizedBox(height: 8),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  for (final w in _windows.entries) ...[
                    ChoiceChip(
                      label: Text(w.value),
                      selected: _weeks == w.key,
                      onSelected: (_) {
                        setState(() => _weeks = w.key);
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
                    icon: Icons.coronavirus_outlined,
                    label: 'Cases',
                    value: '$cases',
                    color: EnhancedTheme.primaryTeal),
                KpiTile(
                    icon: Icons.dangerous_outlined,
                    label: 'Deaths',
                    value: '$deaths',
                    color: EnhancedTheme.errorRed),
                KpiTile(
                    icon: Icons.flag_outlined,
                    label: 'Notifiable rows',
                    value: '$notifiable',
                    color: EnhancedTheme.accentOrange),
              ]),
              const SizedBox(height: 12),
              if (rows.isEmpty)
                const EmptyState(
                  icon: Icons.assignment_turned_in_outlined,
                  title: 'Nothing to report',
                  message: 'No case report carries a disease in this window.',
                  color: EnhancedTheme.successGreen,
                ),
              for (var i = 0; i < rows.length; i++) ...[
                if (i == 0 || rows[i]['epi_week'] != rows[i - 1]['epi_week'])
                  Padding(
                    padding: EdgeInsets.only(top: i == 0 ? 0 : 14, bottom: 6),
                    child: Text('${rows[i]['epi_week']}',
                        style: GoogleFonts.outfit(
                          color: context.hintColor,
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        )),
                  ),
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _IdsrRow(row: rows[i]),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _IdsrRow extends StatelessWidget {
  final Map<String, dynamic> row;
  const _IdsrRow({required this.row});

  @override
  Widget build(BuildContext context) {
    final cfr = row['case_fatality_rate'] as num?;
    final code = '${row['icd10_code'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['disease'] ?? '—'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          if (row['notifiable'] == true)
            const ReportBadge(
                text: 'notifiable', color: EnhancedTheme.accentOrange),
        ]),
        const SizedBox(height: 4),
        Text(
            '${row['cases'] ?? 0} case(s) · ${row['deaths'] ?? 0} death(s)'
            ' · CFR ${pctOf(cfr)}${code.isEmpty ? '' : ' · $code'}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
      ]),
    );
  }
}
