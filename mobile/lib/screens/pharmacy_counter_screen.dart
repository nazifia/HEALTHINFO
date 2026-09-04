import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_dispense_sheet.dart';
import 'pharmacy_sales_screen.dart';

/// The pharmacy counter: today's takings, what to reorder, what is about to
/// expire, and what the insurers still owe — plus the button that starts a sale.
///
/// Four small summaries rather than one big endpoint, because each already
/// exists for its own screen and a failure in one should not blank the others.
class PharmacyCounterScreen extends StatefulWidget {
  const PharmacyCounterScreen({super.key});

  @override
  State<PharmacyCounterScreen> createState() => _PharmacyCounterScreenState();
}

class _CounterData {
  final Map<String, dynamic> sales;
  final Map<String, dynamic> claims;
  final Map<String, dynamic> valuation;
  final List<Map<String, dynamic>> reorder;
  final List<Map<String, dynamic>> expiring;
  const _CounterData(
      this.sales, this.claims, this.valuation, this.reorder, this.expiring);
}

class _PharmacyCounterScreenState extends State<PharmacyCounterScreen> {
  late Future<_CounterData> _future;
  String? _role;

  @override
  void initState() {
    super.initState();
    _future = _load();
    api.myRole().then((r) {
      if (mounted) setState(() => _role = r);
    });
  }

  /// Pull every already-expired batch off the shelf in one go.
  ///
  /// Expired stock still counts as stock on hand until someone writes it off,
  /// which is exactly what makes a valuation wrong. Admin only, and confirmed
  /// first: each batch gets its own write-off movement and none of it comes
  /// back.
  Future<void> _writeOffExpired() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Write off expired stock'),
        content: const Text(
            'Every batch already past its expiry date is taken off the shelf, '
            'batch by batch. This cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Write off')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      final r = await api.post('/api/inventory/batches/write-off-expired/', {});
      if (!mounted) return;
      showSuccess(context, '${(r as Map?)?['message'] ?? 'Done.'}');
      _reload();
    } catch (e) {
      if (mounted) showError(context, '$e');
    }
  }

  String _today() => DateTime.now().toIso8601String().substring(0, 10);

  Future<_CounterData> _load() async {
    final today = _today();
    // One failed panel is not a failed screen: a summary that errors comes back
    // empty and its tiles read "—".
    Future<Map<String, dynamic>> obj(String path,
            [Map<String, String>? query]) async =>
        api
            .get(path, query)
            .then((r) => (r as Map).cast<String, dynamic>())
            .catchError((_) => <String, dynamic>{});
    Future<List<Map<String, dynamic>>> rows(String path,
            [Map<String, String>? query]) async =>
        api
            .getList(path, query)
            .then((r) => r.cast<Map<String, dynamic>>())
            .catchError((_) => <Map<String, dynamic>>[]);

    final results = await Future.wait([
      obj('/api/pharmacy/sales/summary/', {'from': today, 'to': today}),
      obj('/api/pharmacy/claims/summary/'),
      obj('/api/pharmacy/items/valuation/'),
      rows('/api/pharmacy/items/low-stock/'),
      rows('/api/pharmacy/batches/expiring/', {'days': '60'}),
    ]);
    return _CounterData(
      results[0] as Map<String, dynamic>,
      results[1] as Map<String, dynamic>,
      results[2] as Map<String, dynamic>,
      results[3] as List<Map<String, dynamic>>,
      results[4] as List<Map<String, dynamic>>,
    );
  }

  void _reload() => setState(() { _future = _load(); });

  Future<void> _dispense() async {
    final sale = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const DispenseSheet(),
    );
    if (sale == null || !mounted) return;
    showSuccess(context,
        'Sale ${sale['reference']} — patient pays ${money(sale['patient_payable'])}.');
    _reload();
    // Straight into the sale so the counter can take the money and show the
    // receipt without hunting for it in the list.
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => SaleSheet(sale: sale),
    );
    if (mounted) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'fab_dispense_counter',
        onPressed: _dispense,
        backgroundColor: EnhancedTheme.primaryTeal,
        icon: const Icon(Icons.point_of_sale_outlined, color: Colors.white),
        label: const Text('Dispense',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          final f = _load();
          setState(() { _future = f; });
          await f;
        },
        child: FutureBuilder<_CounterData>(
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
                  title: 'Could not load the counter',
                  message: '${snap.error}',
                  color: EnhancedTheme.errorRed,
                ),
              ]);
            }
            final d = snap.data!;
            final owed = num.tryParse('${d.sales['outstanding']}') ?? 0;
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
              children: [
                StatsHeader(
                  icon: Icons.local_pharmacy_outlined,
                  title: 'Pharmacy counter',
                  subtitle: 'Today, ${_today()}',
                  color: EnhancedTheme.primaryTeal,
                ),
                // One row of six: KpiRow lays tiles two to a line, so six fill
                // three even lines where two rows of three left a gap.
                KpiRow(tiles: [
                  KpiTile(
                      icon: Icons.receipt_long_outlined,
                      label: 'Sales today',
                      value: units(d.sales['sales'] ?? 0),
                      color: EnhancedTheme.primaryTeal),
                  KpiTile(
                      icon: Icons.payments_outlined,
                      label: 'Collected',
                      value: money(d.sales['collected'] ?? 0),
                      color: EnhancedTheme.accentCyan),
                  KpiTile(
                      icon: Icons.hourglass_bottom,
                      label: 'Owed by patients',
                      value: money(owed),
                      color: EnhancedTheme.accentOrange),
                  KpiTile(
                      icon: Icons.health_and_safety_outlined,
                      label: 'Owed by insurers',
                      value: money(d.claims['outstanding'] ?? 0),
                      color: EnhancedTheme.infoBlue),
                  KpiTile(
                      icon: Icons.inventory_2_outlined,
                      label: 'Stock at cost',
                      value: money(d.valuation['cost_value'] ?? 0),
                      color: EnhancedTheme.accentPurple),
                  KpiTile(
                      icon: Icons.warning_amber_rounded,
                      label: 'To reorder',
                      value: units(d.reorder.length),
                      color: EnhancedTheme.errorRed),
                ]),
                const SizedBox(height: 12),
                StatSection(
                  icon: Icons.warning_amber_rounded,
                  heading: 'Reorder (${d.reorder.length})',
                  color: EnhancedTheme.errorRed,
                  child: d.reorder.isEmpty
                      ? Text('Nothing to reorder.',
                          style:
                              TextStyle(color: context.hintColor, fontSize: 13))
                      : Column(children: [
                          for (final r in d.reorder.take(8))
                            _Line(
                              title: '${r['name']}',
                              subtitle:
                                  '${units(r['quantity_on_hand'])} on hand · reorder at ${units(r['reorder_level'])}',
                              trailing: money(r['unit_price']),
                            ),
                        ]),
                ),
                StatSection(
                  icon: Icons.event_busy_outlined,
                  heading: 'Expiring within 60 days (${d.expiring.length})',
                  color: EnhancedTheme.accentOrange,
                  trailing: !isPharmacyAdmin(_role)
                      ? null
                      : TextButton.icon(
                          onPressed: _writeOffExpired,
                          style: TextButton.styleFrom(
                              foregroundColor: EnhancedTheme.errorRed),
                          icon: const Icon(Icons.delete_sweep_outlined,
                              size: 18),
                          label: const Text('Write off expired'),
                        ),
                  child: d.expiring.isEmpty
                      ? Text('Nothing expiring.',
                          style:
                              TextStyle(color: context.hintColor, fontSize: 13))
                      : Column(children: [
                          for (final b in d.expiring.take(8))
                            _Line(
                              title: '${b['item_name']}',
                              subtitle:
                                  'Batch ${b['batch_number']} · ${units(b['quantity'])} left',
                              trailing: '${b['expiry_date']}',
                            ),
                        ]),
                ),
                StatSection(
                  icon: Icons.health_and_safety_outlined,
                  heading: 'Insurers',
                  color: EnhancedTheme.infoBlue,
                  child: ((d.claims['by_hmo'] as List?) ?? []).isEmpty
                      ? Text('No claims yet.',
                          style:
                              TextStyle(color: context.hintColor, fontSize: 13))
                      : Column(children: [
                          for (final h in (d.claims['by_hmo'] as List)
                              .cast<Map<String, dynamic>>())
                            _Line(
                              title: '${h['name']}',
                              subtitle:
                                  '${h['claims']} claim(s) · ${money(h['paid'])} paid',
                              trailing: money(h['outstanding']),
                            ),
                        ]),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _Line extends StatelessWidget {
  final String title;
  final String subtitle;
  final String trailing;
  const _Line(
      {required this.title, required this.subtitle, required this.trailing});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text(title,
          style: TextStyle(color: context.labelColor, fontSize: 14)),
      subtitle: Text(subtitle),
      trailing: Text(trailing,
          style: const TextStyle(fontWeight: FontWeight.w700)),
    );
  }
}
