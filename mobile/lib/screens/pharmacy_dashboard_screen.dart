import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/bar_chart.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/live_refresh.dart';

/// A pharmacy's home: today's counter, this month's takings, and the shelf
/// problems — low stock and batches about to expire. Every figure is the
/// /api/reports/* server total; the Pharmacy reports screen has the rest.
class PharmacyDashboardScreen extends StatefulWidget {
  /// Jumps the drawer to a section by its label, as the HMO desk does.
  final void Function(String label)? onOpen;

  const PharmacyDashboardScreen({super.key, this.onOpen});

  @override
  State<PharmacyDashboardScreen> createState() =>
      _PharmacyDashboardScreenState();
}

class _PharmacyDashboardScreenState extends State<PharmacyDashboardScreen>
    with AutomaticKeepAliveClientMixin, LiveRefresh {
  @override
  void refresh() => _reload();

  @override
  bool get wantKeepAlive => true;

  late Future<List<Map<String, dynamic>>> _future = _load();

  Future<List<Map<String, dynamic>>> _load() {
    // One failed call is an empty card, not a failed screen: its tiles read "—".
    Future<Map<String, dynamic>> obj(String path, [Map<String, String>? q]) =>
        api
            .get(path, q)
            .then((r) => (r as Map).cast<String, dynamic>())
            .catchError((_) => <String, dynamic>{});
    return Future.wait([
      obj('/api/reports/sales/', {'period': 'today'}),
      obj('/api/reports/sales/', {'period': 'month'}),
      obj('/api/reports/inventory/'),
    ]);
  }

  void _reload() => setState(() {
        _future = _load();
      });

  Widget? _open(String label) => widget.onOpen == null
      ? null
      : TextButton(
          onPressed: () => widget.onOpen!(label), child: const Text('Open'));

  Widget _hint(String text) =>
      Text(text, style: TextStyle(color: context.hintColor, fontSize: 13));

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
      child: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (!snap.hasData) {
            return const SkeletonCards(cards: 3, statRow: true);
          }
          final [today, month, stock] = snap.data!;
          final low = ((stock['low_stock'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          final expiring = ((stock['expiring_batches'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          final top = ((month['top_items'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          final daily = ((month['daily'] as List?) ?? [])
              .cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              const DashTitleBar(title: 'Pharmacy', subtitle: 'Today and this month'),
              KpiRow(tiles: [
                KpiTile(
                  icon: Icons.point_of_sale_outlined,
                  label: 'Sales today',
                  value: money(today['total_revenue']),
                  color: EnhancedTheme.successGreen,
                ),
                KpiTile(
                  icon: Icons.receipt_outlined,
                  label: 'Transactions today',
                  value: units(today['total_sales']),
                  color: EnhancedTheme.accentCyan,
                ),
                KpiTile(
                  icon: Icons.calendar_month_outlined,
                  label: 'Sales this month',
                  value: money(month['total_revenue']),
                  color: EnhancedTheme.primaryTeal,
                ),
                KpiTile(
                  icon: Icons.inventory_2_outlined,
                  label: 'Stock value (retail)',
                  value: money(stock['retail_value']),
                  color: EnhancedTheme.infoBlue,
                ),
                KpiTile(
                  icon: Icons.warning_amber_outlined,
                  label: 'Low stock items',
                  value: units(stock['low_stock_count']),
                  color: EnhancedTheme.accentOrange,
                ),
                KpiTile(
                  icon: Icons.event_busy_outlined,
                  label: 'Expiring in 30 days',
                  value: units(expiring.length),
                  color: EnhancedTheme.errorRed,
                ),
              ]),
              const SizedBox(height: 12),
              StatSection(
                icon: Icons.show_chart,
                heading: 'Daily sales this month',
                color: EnhancedTheme.successGreen,
                trailing: _open('Sales'),
                child: TrendLineChart(rows: [
                  for (final r in daily)
                    (
                      period: '${r['date']}'.substring(5),
                      value: num.tryParse('${r['revenue']}') ?? 0,
                    ),
                ]),
              ),
              StatSection(
                icon: Icons.bar_chart_outlined,
                heading: 'Top sellers this month',
                color: EnhancedTheme.primaryTeal,
                trailing: _open('Pharmacy reports'),
                child: top.isEmpty
                    ? _hint('Nothing sold this month yet.')
                    : MiniBarChart(rows: [
                        for (final r in top.take(8))
                          (label: '${r['name']}', value: (r['units'] as num?) ?? 0),
                      ]),
              ),
              StatSection(
                icon: Icons.warning_amber_outlined,
                heading: 'Low stock (${low.length})',
                color: EnhancedTheme.accentOrange,
                trailing: _open('Stock items'),
                child: low.isEmpty
                    ? _hint('Everything is above its reorder level.')
                    : Column(children: [
                        for (final r in low.take(8))
                          ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            title: Text('${r['name']}',
                                overflow: TextOverflow.ellipsis),
                            subtitle: Text(
                                'Reorder at ${units(r['reorder_level'])}'),
                            trailing: Text(
                                '${units(r['on_hand'])} ${r['unit'] ?? ''}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                          ),
                      ]),
              ),
              StatSection(
                icon: Icons.event_busy_outlined,
                heading: 'Expiring soon (${expiring.length})',
                color: EnhancedTheme.errorRed,
                trailing: _open('Stock items'),
                child: expiring.isEmpty
                    ? _hint('No batch expires in the next 30 days.')
                    : Column(children: [
                        for (final r in expiring.take(8))
                          ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            title: Text('${r['name']}',
                                overflow: TextOverflow.ellipsis),
                            subtitle: Text(
                                'Batch ${r['batch_number']} · ${r['expiry_date']}'),
                            trailing: Text('${r['days']} days',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                          ),
                      ]),
              ),
            ],
          );
        },
      ),
    );
  }
}
