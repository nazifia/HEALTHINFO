import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/export_csv.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'report_scaffold.dart';

/// IDSR daily epidemiological summary — GET /api/analytics/idsr/.
///
/// Super-admins get the central NCDC collation (/api/analytics/platform/idsr/);
/// everyone else their own facility's return. Response: {"days": N,
/// "summary": [{date, disease, icd10_code, notifiable, notify_immediately,
/// cases, deaths, case_fatality_rate}, ...]} newest day first, plus
/// "immediate": the single cases of an epidemic-prone disease whose 24-hour
/// notification clock is running, oldest first. Sending one
/// (POST /api/case-reports/{id}/notify/) takes it off that list.
///
/// Rows are grouped by day here only for reading — the server already
/// ordered them, so grouping never reorders, it just inserts the headings.
/// The CSV the public-health authority expects is the same ?format=csv the web
/// client downloads — here it goes out through the platform share sheet.
class IdsrScreen extends StatefulWidget {
  const IdsrScreen({super.key});

  @override
  State<IdsrScreen> createState() => _IdsrScreenState();
}

class _IdsrScreenState extends State<IdsrScreen> {
  int _days = 30;
  // Which endpoint answered, so the CSV export pulls the same scope as the
  // rows on screen rather than guessing at the reader's role a second time.
  String _path = '/api/analytics/idsr/';
  late Future<List<Map<String, dynamic>>> _future = _load();

  static const _windows = {7: '7 days', 30: '30 days', 90: '90 days', 180: '6 months'};

  // The 24-hour worklist that came back with the same call. Held apart from
  // the daily rows because it is a different report: one card per case, not
  // per day.
  List<Map<String, dynamic>> _immediate = const [];

  Future<List<Map<String, dynamic>>> _load() async {
    final q = {'days': '$_days'};
    Map data;
    // Platform view is super-admin only; a 403 scopes down to this tenant.
    try {
      data = await api.get('/api/analytics/platform/idsr/', q) as Map;
      _path = '/api/analytics/platform/idsr/';
    } catch (_) {
      data = await api.get('/api/analytics/idsr/', q) as Map;
      _path = '/api/analytics/idsr/';
    }
    _immediate = ((data['immediate'] as List?) ?? []).cast<Map<String, dynamic>>();
    return ((data['summary'] as List?) ?? []).cast<Map<String, dynamic>>();
  }

  void _reload() => setState(() { _future = _load(); });

  /// Mark one case notified, then reload so it leaves the worklist.
  Future<void> _notify(int id) async {
    try {
      await api.post('/api/case-reports/$id/notify/');
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not record the notification: $e')),
      );
    }
  }

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
                title: 'IDSR daily summary',
                subtitle: 'Cases, deaths and case-fatality by day',
                trailing: CsvExportButton(
                  path: _path,
                  filename: 'idsr_${_days}d.csv',
                  query: {'days': '$_days'},
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
                KpiTile(
                    icon: Icons.alarm_outlined,
                    label: 'Notify in 24h',
                    value: '${_immediate.length}',
                    color: EnhancedTheme.errorRed),
              ]),
              const SizedBox(height: 12),
              if (_immediate.isNotEmpty) ...[
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text('Immediate notification (24h)',
                      style: GoogleFonts.outfit(
                        color: context.hintColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 13,
                      )),
                ),
                for (final c in _immediate)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _ImmediateRow(
                      row: c,
                      // Case reports are tenant-scoped, so only a facility
                      // reading its own return can send one. The centre is
                      // watching the same list, not working it.
                      onNotify: _path == '/api/analytics/idsr/'
                          ? () => _notify(c['id'] as int)
                          : null,
                    ),
                  ),
                const SizedBox(height: 14),
              ],
              if (rows.isEmpty)
                const EmptyState(
                  icon: Icons.assignment_turned_in_outlined,
                  title: 'Nothing to report',
                  message: 'No case report carries a disease in this window.',
                  color: EnhancedTheme.successGreen,
                ),
              for (var i = 0; i < rows.length; i++) ...[
                if (i == 0 || rows[i]['date'] != rows[i - 1]['date'])
                  Padding(
                    padding: EdgeInsets.only(top: i == 0 ? 0 : 14, bottom: 6),
                    child: Text('${rows[i]['date']}',
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
          if (row['notify_immediately'] == true)
            const ReportBadge(text: '24h', color: EnhancedTheme.errorRed)
          else if (row['notifiable'] == true)
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


/// One case awaiting immediate notification. Shows the facility and LGA because
/// a super-admin reads this list across every tenant, and the hours elapsed
/// because that is what says how late the notification already is.
class _ImmediateRow extends StatelessWidget {
  final Map<String, dynamic> row;
  /// Null in the central view, where the reader watches rather than sends.
  final VoidCallback? onNotify;
  const _ImmediateRow({required this.row, this.onNotify});

  @override
  Widget build(BuildContext context) {
    final overdue = row['overdue'] == true;
    final hours = (row['hours_elapsed'] as num?)?.toStringAsFixed(0) ?? '?';
    final where = [row['facility'], row['jurisdiction']]
        .map((v) => '${v ?? ''}'.trim())
        .where((v) => v.isNotEmpty)
        .join(' · ');
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['disease'] ?? '—'} · case #${row['id']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
            text: overdue ? 'overdue ${hours}h' : '${hours}h ago',
            color: overdue
                ? EnhancedTheme.errorRed
                : EnhancedTheme.accentOrange,
          ),
        ]),
        const SizedBox(height: 4),
        Text(
            [
              if (where.isNotEmpty) where,
              '${row['severity'] ?? ''}',
              '${row['outcome'] ?? ''}',
            ].where((v) => v.trim().isNotEmpty).join(' · '),
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if (onNotify != null)
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: onNotify,
              icon: const Icon(Icons.send_outlined, size: 18),
              label: const Text('Mark notified'),
              style: TextButton.styleFrom(
                  foregroundColor: EnhancedTheme.primaryTeal),
            ),
          ),
      ]),
    );
  }
}
