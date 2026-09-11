import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';

/// The pharmacy's side of the insurance desk: what the schemes have been
/// billed over a period, what they still owe, and the two queues that stall
/// money — requests the insurer has not answered, and claims nobody has
/// submitted yet.
///
/// Mirrors viewHmo() in web/app.js, dates included: the money narrows to the
/// chosen range, the queues do not. A request left unanswered since last month
/// is exactly the work this screen is for.
class HmoDashboardScreen extends StatefulWidget {
  /// Jumps the drawer to a section by its label, the way the ward tiles do.
  /// Null on a standalone route, where the panels are figures and nothing more.
  final void Function(String label)? onOpen;

  const HmoDashboardScreen({super.key, this.onOpen});

  @override
  State<HmoDashboardScreen> createState() => _HmoDashboardScreenState();
}

/// The summary call's date window. No range is every claim ever raised, which
/// is the figure the counter asks for first; a range is a deliberate narrowing
/// and both ends travel (config.ranges reads from/to).
Map<String, String> hmoRange(DateTimeRange? range) => range == null
    ? const {}
    : {
        'from': range.start.toIso8601String().substring(0, 10),
        'to': range.end.toIso8601String().substring(0, 10),
      };

/// What each scheme still owes, biggest first. The API orders by_hmo by what
/// was claimed, which is not the same ranking — a scheme can be the largest
/// biller and owe nothing.
List<({String label, num value, Color color})> owedByScheme(
        List<Map<String, dynamic>> schemes) =>
    <({String label, num value, Color color})>[
      for (final h in schemes)
        (
          label: '${h['name']}',
          value: num.tryParse('${h['outstanding']}') ?? 0,
          color: EnhancedTheme.infoBlue,
        ),
    ]..sort((a, b) => b.value.compareTo(a.value));

class _HmoData {
  final Map<String, dynamic> claims;
  final List<Map<String, dynamic>> waiting;
  final List<Map<String, dynamic>> drafts;
  final List<Map<String, dynamic>> dependents;
  const _HmoData(this.claims, this.waiting, this.drafts, this.dependents);
}

class _HmoDashboardScreenState extends State<HmoDashboardScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<_HmoData> _future;

  // Empty is every claim ever raised, which is the figure the counter asks for
  // first. A range is a deliberate narrowing.
  DateTimeRange? _range;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  String _day(DateTime d) => d.toIso8601String().substring(0, 10);

  Future<_HmoData> _load() async {
    // One failed panel is not a failed screen, same as the counter: a call that
    // errors comes back empty and its tiles read "—".
    Future<Map<String, dynamic>> obj(String path,
            [Map<String, String>? query]) async =>
        api
            .get(path, query)
            .then((r) => (r as Map).cast<String, dynamic>())
            .catchError((_) => <String, dynamic>{});
    Future<List<Map<String, dynamic>>> rows(
            String path, Map<String, String> query) async =>
        api
            .getList(path, query)
            .then((r) => r.cast<Map<String, dynamic>>())
            .catchError((_) => <Map<String, dynamic>>[]);

    final results = await Future.wait([
      obj('/api/pharmacy/claims/summary/', hmoRange(_range)),
      rows('/api/pharmacy/pre-authorizations/',
          {'status': 'requested', 'ordering': '-created_at', 'page_size': '8'}),
      rows('/api/pharmacy/claims/',
          {'status': 'draft', 'ordering': '-created_at', 'page_size': '8'}),
      rows('/api/pharmacy/dependents/',
          {'status': 'pending', 'ordering': '-created_at', 'page_size': '8'}),
    ]);
    return _HmoData(
      results[0] as Map<String, dynamic>,
      results[1] as List<Map<String, dynamic>>,
      results[2] as List<Map<String, dynamic>>,
      results[3] as List<Map<String, dynamic>>,
    );
  }

  void _reload() => setState(() {
        _future = _load();
      });

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

  String _rowTitle(Map row) {
    for (final k in [
      'reference', 'claim_number', 'full_name', 'patient_name', 'hmo_name'
    ]) {
      final v = row[k];
      if (v != null && '$v'.trim().isNotEmpty) return '$v';
    }
    return 'Record #${row['id']}';
  }

  String _rowSubtitle(Map row) {
    final at = '${row['created_at'] ?? ''}';
    final when =
        at.length >= 16 ? at.substring(0, 16).replaceFirst('T', ' ') : at;
    final scheme = '${row['hmo_name'] ?? ''}';
    return [scheme, when].where((s) => s.isNotEmpty).join(' · ');
  }

  /// One queue: the newest few rows, each tapping through to the screen that
  /// can act on it.
  Widget _queue({
    required IconData icon,
    required String heading,
    required String label,
    required String empty,
    required Color color,
    required List<Map<String, dynamic>> rows,
    required String Function(Map row) trailing,
  }) {
    return StatSection(
      icon: icon,
      heading: heading,
      color: color,
      trailing: widget.onOpen == null
          ? null
          : TextButton(
              onPressed: () => widget.onOpen!(label),
              child: const Text('Open')),
      child: rows.isEmpty
          ? Text(empty,
              style: TextStyle(color: context.hintColor, fontSize: 13))
          : Column(children: [
              for (final r in rows)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(_rowTitle(r), overflow: TextOverflow.ellipsis),
                  subtitle: Text(_rowSubtitle(r)),
                  trailing: Text(trailing(r),
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  onTap: widget.onOpen == null
                      ? null
                      : () => widget.onOpen!(label),
                ),
            ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
        setState(() {
          _future = f;
        });
        await f;
      },
      child: FutureBuilder<_HmoData>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const SkeletonCards(cards: 3, statRow: true);
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Could not load the HMO desk',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
                action:
                    TextButton(onPressed: _reload, child: const Text('Retry')),
              ),
            ]);
          }
          final d = snap.data!;
          final schemes = ((d.claims['by_hmo'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          final bars = owedByScheme(schemes);
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              StatsHeader(
                icon: Icons.health_and_safety_outlined,
                title: 'Insurance',
                subtitle: _range == null
                    ? 'All claims · tap the dates to narrow'
                    : '${_day(_range!.start)} to ${_day(_range!.end)}',
                color: EnhancedTheme.infoBlue,
                trailing: IconButton(
                  tooltip: 'Pick a period',
                  icon: const Icon(Icons.date_range_outlined),
                  onPressed: _pickRange,
                ),
              ),
              if (_range != null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () => setState(() {
                      _range = null;
                      _future = _load();
                    }),
                    icon: const Icon(Icons.clear, size: 16),
                    label: const Text('All time'),
                  ),
                ),
              // The two queues lead: they are work waiting, not figures.
              KpiRow(tiles: [
                KpiTile(
                    icon: Icons.verified_user_outlined,
                    label: 'Awaiting authorisation',
                    value: units(d.waiting.length),
                    color: EnhancedTheme.accentOrange),
                KpiTile(
                    icon: Icons.drafts_outlined,
                    label: 'Claims to submit',
                    value: units(d.drafts.length),
                    color: EnhancedTheme.errorRed),
                KpiTile(
                    icon: Icons.family_restroom_outlined,
                    label: 'Dependents to approve',
                    value: units(d.dependents.length),
                    color: EnhancedTheme.accentPurple),
                KpiTile(
                    icon: Icons.health_and_safety_outlined,
                    label: 'Schemes billed',
                    value: units(schemes.length),
                    color: EnhancedTheme.primaryTeal),
                KpiTile(
                    icon: Icons.request_quote_outlined,
                    label: 'Claimed',
                    value: money(d.claims['claimed'] ?? 0),
                    color: EnhancedTheme.accentCyan),
                KpiTile(
                    icon: Icons.payments_outlined,
                    label: 'Paid',
                    value: money(d.claims['paid'] ?? 0),
                    color: EnhancedTheme.successGreen),
                KpiTile(
                    icon: Icons.hourglass_bottom,
                    label: 'Owed by insurers',
                    value: money(d.claims['outstanding'] ?? 0),
                    color: EnhancedTheme.infoBlue),
              ]),
              const SizedBox(height: 12),
              _queue(
                icon: Icons.verified_user_outlined,
                heading: 'Waiting on the insurer (${d.waiting.length})',
                label: 'Authorisations',
                empty: 'Nothing awaiting an answer.',
                color: EnhancedTheme.accentOrange,
                rows: d.waiting,
                trailing: (r) => money(r['requested_amount'] ?? 0),
              ),
              _queue(
                icon: Icons.drafts_outlined,
                heading: 'Claims not submitted yet (${d.drafts.length})',
                label: 'HMO claims',
                empty: 'Nothing left in draft.',
                color: EnhancedTheme.errorRed,
                rows: d.drafts,
                trailing: (r) => money(r['amount'] ?? 0),
              ),
              // Raised by principals from the portal; answered on the
              // Schemes screen's Dependents tab.
              _queue(
                icon: Icons.family_restroom_outlined,
                heading: 'Dependents awaiting approval (${d.dependents.length})',
                label: 'Schemes',
                empty: 'Nobody waiting on an answer.',
                color: EnhancedTheme.accentPurple,
                rows: d.dependents,
                trailing: (r) => '${r['relationship'] ?? ''}',
              ),
              StatSection(
                icon: Icons.bar_chart_outlined,
                heading: 'Owed by scheme',
                color: EnhancedTheme.infoBlue,
                trailing: widget.onOpen == null
                    ? null
                    : TextButton(
                        onPressed: () => widget.onOpen!('Schemes'),
                        child: const Text('Open')),
                child: bars.isEmpty
                    ? Text('No claims in this period.',
                        style:
                            TextStyle(color: context.hintColor, fontSize: 13))
                    : ComparisonBars(
                        rows: bars,
                        onTap: widget.onOpen == null
                            ? null
                            : (_) => widget.onOpen!('Schemes'),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}
