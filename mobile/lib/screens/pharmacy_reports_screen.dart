import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/stats_kit.dart';

/// Pharmacy reports — the /api/reports/* endpoints in one scroll.
///
/// Each card fetches its own endpoint and degrades on its own: a member of
/// staff who may see their own takings but not everyone's gets that card
/// filled and the rest unchanged, rather than a blank page.
///
/// Every figure here is the server's. The client picks the period and draws
/// what comes back — money is totalled once, where the rows are.
class PharmacyReportsScreen extends StatefulWidget {
  const PharmacyReportsScreen({super.key});

  @override
  State<PharmacyReportsScreen> createState() => _PharmacyReportsScreenState();
}

class _PharmacyReportsScreenState extends State<PharmacyReportsScreen> {
  String _period = 'month';
  late Future<_Reports> _future = _load();

  // The named month behind the monthly card. It steps on its own arrows rather
  // than off the period chips: the other reports answer "this quarter", this
  // one answers "March", and the server zero-fills the days either way.
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);
  late Future<Map<String, dynamic>?> _monthly = _loadMonthly();

  static const _periods = {
    'today': 'Today',
    'week': 'Last 7 days',
    'month': 'This month',
    'quarter': 'This quarter',
    'year': 'This year',
  };

  Future<dynamic> _one(String path) async {
    try {
      return await api.get(path, {'period': _period});
    } catch (_) {
      return null;
    }
  }

  Future<_Reports> _load() async {
    final r = await Future.wait([
      _one('/api/reports/sales/'),
      _one('/api/reports/profit/'),
      _one('/api/reports/inventory/'),
      _one('/api/reports/customers/'),
      _one('/api/reports/cashier-sales/'),
      _one('/api/reports/staff-performance/'),
    ]);
    Map<String, dynamic>? m(int i) => (r[i] as Map?)?.cast<String, dynamic>();
    return _Reports(
      sales: m(0),
      profit: m(1),
      inventory: m(2),
      customers: m(3),
      cashiers: m(4),
      staff: m(5),
    );
  }

  Future<Map<String, dynamic>?> _loadMonthly() async {
    try {
      final r = await api.get('/api/reports/monthly/',
          {'year': '${_month.year}', 'month': '${_month.month}'});
      return (r as Map).cast<String, dynamic>();
    } catch (_) {
      return null; // same degrade-alone rule as every other card here
    }
  }

  void _stepMonth(int months) {
    final next = stepMonth(_month, months, DateTime.now());
    if (next == _month) return;
    setState(() {
      _month = next;
      _monthly = _loadMonthly();
    });
  }

  void _reload() => setState(() {
        _future = _load();
        _monthly = _loadMonthly();
      });

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        _reload();
        await _future;
      },
      child: FutureBuilder<_Reports>(
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
                title: 'Could not load reports',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final r = snap.data!;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              DashTitleBar(
                title: 'Pharmacy reports',
                subtitle: r.sales == null
                    ? _periods[_period] ?? _period
                    : '${r.sales!['date_from']} → ${r.sales!['date_to']}',
              ),
              const SizedBox(height: 8),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  for (final p in _periods.entries) ...[
                    ChoiceChip(
                      label: Text(p.value),
                      selected: _period == p.key,
                      onSelected: (_) {
                        setState(() => _period = p.key);
                        _reload();
                      },
                    ),
                    const SizedBox(width: 8),
                  ],
                ]),
              ),
              const SizedBox(height: 12),
              if (r.sales != null) _SalesCard(s: r.sales!),
              if (r.profit != null) _ProfitCard(p: r.profit!),
              if (r.inventory != null) _InventoryCard(i: r.inventory!),
              if (r.customers != null) _CustomersCard(c: r.customers!),
              if (r.cashiers != null) _CashierCard(c: r.cashiers!),
              if (r.staff != null) _StaffCard(s: r.staff!),
              FutureBuilder<Map<String, dynamic>?>(
                future: _monthly,
                builder: (context, m) => m.data == null
                    ? const SizedBox.shrink()
                    : _MonthlyCard(
                        m: m.data!,
                        month: _month,
                        onStep: _stepMonth,
                      ),
              ),
              if (r.isEmpty)
                const EmptyState(
                  icon: Icons.lock_outline,
                  title: 'No reports available',
                  message: 'Reports are for pharmacy staff on this tenant.',
                ),
            ],
          );
        },
      ),
    );
  }
}

class _Reports {
  final Map<String, dynamic>? sales;
  final Map<String, dynamic>? profit;
  final Map<String, dynamic>? inventory;
  final Map<String, dynamic>? customers;
  final Map<String, dynamic>? cashiers;
  final Map<String, dynamic>? staff;

  const _Reports({
    this.sales,
    this.profit,
    this.inventory,
    this.customers,
    this.cashiers,
    this.staff,
  });

  bool get isEmpty =>
      sales == null &&
      profit == null &&
      inventory == null &&
      customers == null &&
      cashiers == null &&
      staff == null;
}

/// Move [month] by [months], stopping at the month [now] falls in.
///
/// The API would happily zero-fill a month that has not happened, so the
/// forward edge is held here. Returns [month] unchanged when the step would
/// cross it, which is what tells the caller not to refetch.
DateTime stepMonth(DateTime month, int months, DateTime now) {
  final next = DateTime(month.year, month.month + months);
  final current = DateTime(now.year, now.month);
  return next.isAfter(current) ? DateTime(month.year, month.month) : next;
}

/// One named month, day by day — GET /api/reports/monthly/.
///
/// The other cards answer a period ("this quarter"); this one answers a month
/// by name, so it carries its own arrows. The series is zero-filled by the
/// server, so every day of the month is a point whether or not it sold.
class _MonthlyCard extends StatelessWidget {
  final Map<String, dynamic> m;
  final DateTime month;
  final void Function(int months) onStep;
  const _MonthlyCard(
      {required this.m, required this.month, required this.onStep});

  static const _names = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  @override
  Widget build(BuildContext context) {
    final daily = ((m['daily'] ?? []) as List).cast<Map<String, dynamic>>();
    final now = DateTime.now();
    final atCurrent = month.year == now.year && month.month == now.month;
    return PanelCard(
      title: 'Month',
      accent: EnhancedTheme.accentPurple,
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          icon: const Icon(Icons.chevron_left),
          tooltip: 'Previous month',
          onPressed: () => onStep(-1),
        ),
        Text('${_names[month.month - 1]} ${month.year}',
            style: TextStyle(
                color: context.labelColor, fontWeight: FontWeight.w700)),
        IconButton(
          icon: const Icon(Icons.chevron_right),
          tooltip: 'Next month',
          onPressed: atCurrent ? null : () => onStep(1),
        ),
      ]),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.payments_outlined,
              label: 'Revenue',
              value: money(m['total_revenue']),
              color: EnhancedTheme.accentPurple),
          KpiTile(
              icon: Icons.receipt_long_outlined,
              label: 'Sales',
              value: units(m['total_sales']),
              color: EnhancedTheme.accentCyan),
        ]),
        if (daily.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('Daily revenue',
              style: TextStyle(
                  color: context.labelColor, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Sparkline(
            values: [
              for (final d in daily) num.tryParse('${d['revenue']}') ?? 0
            ],
            color: EnhancedTheme.accentPurple,
          ),
        ],
      ]),
    );
  }
}

class _SalesCard extends StatelessWidget {
  final Map<String, dynamic> s;
  const _SalesCard({required this.s});

  @override
  Widget build(BuildContext context) {
    final methods = (s['payment_methods'] as Map?) ?? const {};
    final net = (s['net'] as Map?) ?? const {};
    final expenses = (s['expenses'] as Map?) ?? const {};
    final daily = ((s['daily'] ?? []) as List).cast<Map<String, dynamic>>();
    final top = ((s['top_items'] ?? []) as List).cast<Map<String, dynamic>>();
    return PanelCard(
      title: 'Sales',
      accent: EnhancedTheme.primaryTeal,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.payments_outlined,
              label: 'Revenue',
              value: money(s['total_revenue']),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.receipt_long_outlined,
              label: 'Sales',
              value: units(s['total_sales']),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.undo_outlined,
              label: 'Refunded',
              value: money(s['total_refunds']),
              color: EnhancedTheme.accentOrange),
        ]),
        const SizedBox(height: 8),
        // Money *received*, so top-ups count and wallet spends do not — that
        // money was banked when it was paid in.
        Text('Money received',
            style: TextStyle(
                color: context.labelColor, fontWeight: FontWeight.w700)),
        ComparisonBars(rows: [
          (
            label: 'Cash',
            value: num.tryParse('${methods['cash']}') ?? 0,
            color: EnhancedTheme.primaryTeal
          ),
          (
            label: 'Card',
            value: num.tryParse('${methods['card']}') ?? 0,
            color: EnhancedTheme.accentCyan
          ),
          (
            label: 'Transfer',
            value: num.tryParse('${methods['transfer']}') ?? 0,
            color: EnhancedTheme.accentOrange
          ),
          (
            label: 'Wallet top-ups',
            value: num.tryParse('${methods['wallet']}') ?? 0,
            color: EnhancedTheme.successGreen
          ),
        ]),
        const SizedBox(height: 8),
        _Line('Retail', money(s['total_retail'])),
        _Line('Wholesale', money(s['total_wholesale'])),
        _Line('Credit sales',
            '${money(s['credit_sales'])} (${units(s['credit_count'])})'),
        _Line('Expenses', money(expenses['total'])),
        _Line('Net', money(net['total']), bold: true),
        if (daily.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('Daily revenue',
              style: TextStyle(
                  color: context.labelColor, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Sparkline(
            values: [
              for (final d in daily) num.tryParse('${d['revenue']}') ?? 0
            ],
          ),
        ],
        if (top.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('Best sellers',
              style: TextStyle(
                  color: context.labelColor, fontWeight: FontWeight.w700)),
          for (final t in top.take(5))
            _Line('${t['name']} · ${units(t['units'])} units',
                money(t['revenue'])),
        ],
      ]),
    );
  }
}

class _ProfitCard extends StatelessWidget {
  final Map<String, dynamic> p;
  const _ProfitCard({required this.p});

  @override
  Widget build(BuildContext context) {
    final coverage = (num.tryParse('${p['cost_coverage']}') ?? 0) * 100;
    return PanelCard(
      title: 'Profit',
      accent: EnhancedTheme.successGreen,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.trending_up_outlined,
              label: 'Profit',
              value: money(p['profit']),
              color: EnhancedTheme.successGreen),
          KpiTile(
              icon: Icons.shopping_bag_outlined,
              label: 'Cost of goods',
              value: money(p['cost']),
              color: EnhancedTheme.accentOrange),
          KpiTile(
              icon: Icons.percent_outlined,
              label: 'Margin',
              value: '${p['margin'] ?? 0}%',
              color: EnhancedTheme.accentCyan),
        ]),
        const SizedBox(height: 8),
        // Below 100%, some lines carried no cost price: the profit above is
        // optimistic by however much those lines cost to buy.
        Text(
            p['estimated'] == true
                ? 'Nothing sold carried a cost price — this is revenue, not profit.'
                : 'Cost recorded on ${coverage.toStringAsFixed(0)}% of line revenue.',
            style: TextStyle(color: context.hintColor, fontSize: 12)),
      ]),
    );
  }
}

class _InventoryCard extends StatelessWidget {
  final Map<String, dynamic> i;
  const _InventoryCard({required this.i});

  @override
  Widget build(BuildContext context) {
    final expiring = (i['expiring'] as Map?) ?? const {};
    final expired = (i['expired'] as Map?) ?? const {};
    final low = ((i['low_stock'] ?? []) as List).cast<Map<String, dynamic>>();
    return PanelCard(
      title: 'Inventory',
      accent: EnhancedTheme.accentCyan,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.inventory_2_outlined,
              label: 'Items',
              value: units(i['active_items']),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.savings_outlined,
              label: 'At cost',
              value: money(i['cost_value']),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.sell_outlined,
              label: 'At retail',
              value: money(i['retail_value']),
              color: EnhancedTheme.successGreen),
        ]),
        const SizedBox(height: 8),
        _Line('Low stock', units(i['low_stock_count'])),
        _Line('Expiring soon',
            '${units(expiring['units'])} units · ${money(expiring['cost_value'])}'),
        _Line('Already expired',
            '${units(expired['units'])} units · ${money(expired['cost_value'])}'),
        if (low.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Running out',
              style: TextStyle(
                  color: context.labelColor, fontWeight: FontWeight.w700)),
          for (final l in low.take(5))
            _Line('${l['name']}',
                '${units(l['quantity_on_hand'] ?? l['quantity'])} left'),
        ],
      ]),
    );
  }
}

class _CustomersCard extends StatelessWidget {
  final Map<String, dynamic> c;
  const _CustomersCard({required this.c});

  @override
  Widget build(BuildContext context) {
    final top =
        ((c['top_customers'] ?? []) as List).cast<Map<String, dynamic>>();
    return PanelCard(
      title: 'Customers',
      accent: EnhancedTheme.primaryTeal,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.groups_outlined,
              label: 'On the books',
              value: units(c['total']),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.account_balance_wallet_outlined,
              label: 'Wallets hold',
              value: money(c['wallet_balance']),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.money_off_outlined,
              label: 'Owed to us',
              value: money(c['outstanding_debt']),
              color: EnhancedTheme.errorRed),
        ]),
        if (top.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Biggest spenders',
              style: TextStyle(
                  color: context.labelColor, fontWeight: FontWeight.w700)),
          for (final t in top.take(5))
            _Line('${t['name']} · ${units(t['sales'])} sales',
                money(t['spent'])),
        ],
      ]),
    );
  }
}

class _CashierCard extends StatelessWidget {
  final Map<String, dynamic> c;
  const _CashierCard({required this.c});

  @override
  Widget build(BuildContext context) {
    final staff = ((c['staff'] ?? []) as List).cast<Map<String, dynamic>>();
    return PanelCard(
      title: c['all_staff'] == true ? 'Takings by person' : 'My takings',
      accent: EnhancedTheme.accentOrange,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _Line('Total taken', money(c['total_amount']), bold: true),
        _Line('Sales', units(c['total_sales'])),
        const SizedBox(height: 4),
        for (final s in staff) ...[
          _Line('${s['name']} (${s['role']})', money(s['amount'])),
          // How the money arrived matters at close: only the cash half has to
          // be in a drawer.
          Text(
            ((s['by_method'] as Map?) ?? const {})
                .entries
                .map((e) => '${e.key} ${money(e.value)}')
                .join(' · '),
            style: TextStyle(color: context.hintColor, fontSize: 12),
          ),
        ],
      ]),
    );
  }
}

class _StaffCard extends StatelessWidget {
  final Map<String, dynamic> s;
  const _StaffCard({required this.s});

  @override
  Widget build(BuildContext context) {
    final staff = ((s['staff'] ?? []) as List).cast<Map<String, dynamic>>();
    return PanelCard(
      title: 'Staff performance',
      accent: EnhancedTheme.successGreen,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _Line('Total payout', money(s['total_payout']), bold: true),
        const SizedBox(height: 4),
        // Staff with no commission row earn nothing rather than being left
        // out — "sold a lot, paid nothing" is worth seeing.
        for (final p in staff)
          _Line(
              '${p['name']} · ${money(p['amount'])} sold @ ${p['rate']}%',
              money(p['payout'])),
      ]),
    );
  }
}

class _Line extends StatelessWidget {
  final String label;
  final String value;
  final bool bold;
  const _Line(this.label, this.value, {this.bold = false});

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
        color: bold ? context.labelColor : context.hintColor,
        fontSize: bold ? 14 : 13,
        fontWeight: bold ? FontWeight.w700 : FontWeight.w500);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Flexible(child: Text(label, style: style, overflow: TextOverflow.ellipsis)),
        const SizedBox(width: 8),
        Text(value, style: style),
      ]),
    );
  }
}
