import 'package:flutter/material.dart';

import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'report_scaffold.dart';

/// Stock ledger — GET /api/pharmacy/movements/.
///
/// Every unit that entered or left, and why. Append-only on the server: a
/// mistake is corrected by another movement, never by an edit, so there is no
/// form behind this screen and no card action.
///
/// `quantity` is signed — positive in, negative out — so the "Net" figure is
/// the net movement of what is on screen, not turnover.
class StockLedgerScreen extends StatelessWidget {
  const StockLedgerScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/movements/',
      fabLabel: '',
      showFab: false,
      emptyIcon: Icons.receipt_long_outlined,
      emptyTitle: 'No movements',
      emptyMessage: 'Rows appear as stock is received, dispensed or counted.',
      savedMessage: '',
      filters: const [
        ReportFilter(param: 'kind', anyLabel: 'Any kind', options: {
          'receipt': 'Received',
          'dispense': 'Dispensed',
          'return': 'Returned',
          'adjustment': 'Count correction',
          'write_off': 'Written off',
          'transfer': 'Transferred',
        }),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _MovementCard(row: row),
      form: (_) => const SizedBox.shrink(),
    );
  }
}

/// Split a page of movements into units in, units out and the net of the two.
///
/// `quantity` is signed on the wire, so the two sides come out of one column:
/// in and out are reported unsigned, and `net` keeps the sign.
({num into, num out, num net}) ledgerTotals(List<Map<String, dynamic>> rows) {
  num into = 0, out = 0;
  for (final r in rows) {
    final q = (r['quantity'] as num?) ?? 0;
    if (q.isNegative) {
      out += q.abs();
    } else {
      into += q;
    }
  }
  return (into: into, out: out, net: into - out);
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final t = ledgerTotals(items);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.receipt_long_outlined,
          title: 'Stock ledger',
          subtitle: '${items.length} movement(s) on this page',
          color: EnhancedTheme.primaryTeal,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.south_west,
              label: 'Units in',
              value: units(t.into),
              color: EnhancedTheme.successGreen),
          KpiTile(
              icon: Icons.north_east,
              label: 'Units out',
              value: units(t.out),
              color: EnhancedTheme.accentOrange),
          KpiTile(
              icon: Icons.functions,
              label: 'Net',
              value: units(t.net),
              color: EnhancedTheme.accentCyan),
        ]),
      ]),
    );
  }
}

class _MovementCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _MovementCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final q = (row['quantity'] as num?) ?? 0;
    final incoming = !q.isNegative;
    final reason = '${row['reason'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['item_name'] ?? '—'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          Text('${incoming ? '+' : '−'}${units(q.abs())}',
              style: TextStyle(
                  color: incoming
                      ? EnhancedTheme.successGreen
                      : EnhancedTheme.accentOrange,
                  fontWeight: FontWeight.w800,
                  fontSize: 15)),
        ]),
        const SizedBox(height: 4),
        Row(children: [
          Expanded(
            child: Text(
                '${row['user_name'] ?? '—'}'
                ' · ${'${row['created_at']}'.split('T').first}'
                '${reason.isEmpty ? '' : ' · $reason'}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
          ),
          ReportBadge(
              text: '${row['kind']}', color: _kindColor('${row['kind']}')),
        ]),
      ]),
    );
  }
}

/// The ledger's kinds are not workflow states, so they get their own mapping
/// rather than bending [statusColor] to cover both.
Color _kindColor(String kind) => switch (kind) {
      'receipt' || 'return' => EnhancedTheme.successGreen,
      'dispense' || 'transfer' => EnhancedTheme.accentCyan,
      'write_off' => EnhancedTheme.errorRed,
      _ => EnhancedTheme.accentOrange,
    };
