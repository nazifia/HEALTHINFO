import 'package:flutter/material.dart';

import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Dispensing log — GET /api/pos/dispensing-log/.
///
/// Every item handed over, across every sale: who dispensed it, when, and
/// whether any of it came back. Written by the sale, never by hand — so this
/// screen is read-only on purpose, and there is no form behind it.
class DispensingLogScreen extends StatelessWidget {
  const DispensingLogScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pos/dispensing-log/',
      searchHint: 'Drug or brand…',
      fabLabel: '',
      showFab: false,
      emptyIcon: Icons.medication_outlined,
      emptyTitle: 'Nothing dispensed yet',
      emptyMessage: 'Rows appear here as sales are made.',
      savedMessage: '',
      filters: const [
        ReportFilter(param: 'status', anyLabel: 'Any state', options: {
          'dispensed': 'Dispensed',
          'partially_returned': 'Part returned',
          'returned': 'Returned',
        }),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _LogCard(row: row),
      form: (_) => const SizedBox.shrink(),
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final dispensed = items.fold<num>(
        0, (t, r) => t + (num.tryParse('${r['quantity']}') ?? 0));
    final value = items.fold<num>(
        0, (t, r) => t + (num.tryParse('${r['amount']}') ?? 0));
    final back = items.where((r) => r['status'] != 'dispensed').length;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.medication_outlined,
          title: 'Dispensing log',
          subtitle: '${items.length} line(s) on this page',
          color: EnhancedTheme.primaryTeal,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.inventory_2_outlined,
              label: 'Units out',
              value: units(dispensed),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.payments_outlined,
              label: 'Value',
              value: money(value),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.undo_outlined,
              label: 'Came back',
              value: units(back),
              color: EnhancedTheme.accentOrange),
        ]),
      ]),
    );
  }
}

class _LogCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _LogCard({required this.row});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['name']} ×${row['quantity']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          Text(money(row['amount']),
              style: TextStyle(
                  color: context.labelColor,
                  fontWeight: FontWeight.w800,
                  fontSize: 15)),
        ]),
        const SizedBox(height: 4),
        Row(children: [
          Expanded(
            child: Text(
                '${row['dispenser'] ?? '—'} · ${row['sale_reference'] ?? ''}'
                ' · ${'${row['created_at']}'.split('T').first}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
          ),
          if (row['status'] != 'dispensed')
            ReportBadge(
                text: '${row['status']}', color: statusColor(row['status'])),
        ]),
      ]),
    );
  }
}

/// Returns — GET /api/pos/returns/.
///
/// What has come back and what was refunded for it. A return is taken on the
/// sale it belongs to, so this list only reads them back.
class ReturnsScreen extends StatelessWidget {
  const ReturnsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pos/returns/',
      fabLabel: '',
      showFab: false,
      emptyIcon: Icons.undo_outlined,
      emptyTitle: 'Nothing returned',
      emptyMessage: 'Take a return on the sale it belongs to.',
      savedMessage: '',
      filters: const [
        ReportFilter(
            param: 'refund_method',
            anyLabel: 'Any refund',
            options: {
              'cash': 'Cash',
              'wallet': 'To wallet',
              'original': 'Original method',
            }),
      ],
      card: (row, reload, edit) => _ReturnCard(row: row),
      form: (_) => const SizedBox.shrink(),
    );
  }
}

class _ReturnCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _ReturnCard({required this.row});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['item_name']} ×${row['quantity']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          Text('−${money(row['amount'])}',
              style: const TextStyle(
                  color: EnhancedTheme.errorRed,
                  fontWeight: FontWeight.w800,
                  fontSize: 15)),
        ]),
        const SizedBox(height: 4),
        Text(
            '${row['sale_reference'] ?? ''} · refunded '
            '${row['refund_method']} · ${'${row['created_at']}'.split('T').first}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if ('${row['reason'] ?? ''}'.trim().isNotEmpty)
          Text('${row['reason']}',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
      ]),
    );
  }
}
