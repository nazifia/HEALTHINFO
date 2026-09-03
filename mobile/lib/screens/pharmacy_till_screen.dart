import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_sales_screen.dart' show askAmount, askText;
import 'report_scaffold.dart';

/// Cash drawer — GET /api/pharmacy/till-sessions/.
///
/// A cashier opens a drawer with its float, cash payments book themselves into
/// it as they are taken, and closing it is one count against what should be
/// there. The variance is recorded, never corrected: a short drawer is a fact
/// to explain, not a number to adjust until it agrees.
class PharmacyTillScreen extends StatelessWidget {
  const PharmacyTillScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/till-sessions/',
      fabLabel: 'Open drawer',
      emptyIcon: Icons.point_of_sale_outlined,
      emptyTitle: 'No drawer opened yet',
      emptyMessage: 'Tap "Open drawer" and count in the float.',
      savedMessage: 'Drawer opened.',
      filters: const [
        ReportFilter(param: 'status', anyLabel: 'Any state', options: {
          'open': 'Open',
          'closed': 'Closed',
        }),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _TillCard(row: row),
      onTap: (row) => _openTill(context, row),
      form: (_) => const _OpenTillForm(),
    );
  }

  static Future<void> _openTill(
      BuildContext context, Map<String, dynamic> row) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => TillSheet(session: row),
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    final open = items.where((r) => r['status'] == 'open').toList();
    // Only a counted drawer has a variance, so the over/short total comes from
    // the closed ones alone.
    final counted = items.where((r) => r['status'] == 'closed');
    num sum(Iterable<Map<String, dynamic>> rows, String key) => rows.fold<num>(
        0, (total, r) => total + (num.tryParse('${r[key]}') ?? 0));
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.point_of_sale_outlined,
          title: 'Cash drawer',
          subtitle: open.isEmpty
              ? 'No drawer open'
              : '${open.length} drawer${open.length == 1 ? '' : 's'} open',
          color: EnhancedTheme.primaryTeal,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.savings_outlined,
              label: 'Expected now',
              value: money(sum(open, 'expected_amount')),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.payments_outlined,
              label: 'Taken',
              value: money(sum(open, 'cash_in')),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.balance_outlined,
              label: 'Over / short',
              value: money(sum(counted, 'variance')),
              color: EnhancedTheme.accentOrange),
        ]),
      ]),
    );
  }
}

Color _varianceColor(Object? variance) {
  final v = num.tryParse('${variance ?? ''}');
  if (v == null || v == 0) return EnhancedTheme.successGreen;
  return v < 0 ? EnhancedTheme.errorRed : EnhancedTheme.accentOrange;
}

class _TillCard extends StatelessWidget {
  final Map<String, dynamic> row;
  const _TillCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final open = row['status'] == 'open';
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['opened_by_name'] ?? 'Cashier'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
            text: '${row['status']}',
            color: open
                ? EnhancedTheme.accentOrange
                : _varianceColor(row['variance']),
          ),
        ]),
        const SizedBox(height: 6),
        Text(
            'Float ${money(row['opening_float'])} · '
            'Expected ${money(row['expected_amount'])}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        const SizedBox(height: 4),
        Text(
          open
              ? '${money(row['cash_in'])} in · ${money(row['change_out'])} change'
              : 'Counted ${money(row['counted_amount'])} · '
                  '${money(row['variance'])} over/short',
          style: TextStyle(color: context.hintColor, fontSize: 13),
        ),
      ]),
    );
  }
}

/// One drawer in full, with the count that closes it.
class TillSheet extends StatefulWidget {
  final Map<String, dynamic> session;
  const TillSheet({super.key, required this.session});

  @override
  State<TillSheet> createState() => _TillSheetState();
}

class _TillSheetState extends State<TillSheet> {
  late Map<String, dynamic> _till = widget.session;
  bool _busy = false;

  Future<void> _refresh() async {
    final fresh = await api.get('/api/pharmacy/till-sessions/${_till['id']}/');
    if (mounted) setState(() => _till = (fresh as Map).cast<String, dynamic>());
  }

  Future<void> _close() async {
    // The expected figure seeds the field: the cashier types what was actually
    // counted, and the difference stands as it falls.
    final counted = await askAmount(
        context, 'Close drawer', 'Counted cash (₦)', '${_till['expected_amount']}');
    if (counted == null) return;
    if (!mounted) return;
    final notes = await askText(context, 'Close drawer', 'Note (optional)');
    setState(() => _busy = true);
    try {
      final r = await api.post(
          '/api/pharmacy/till-sessions/${_till['id']}/close/',
          {'amount': counted, 'notes': notes ?? ''});
      await _refresh();
      if (mounted) showSuccess(context, '${(r as Map?)?['message'] ?? 'Done.'}');
    } catch (e) {
      if (mounted) showError(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final open = _till['status'] == 'open';
    return Container(
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(
                child: Text('${_till['opened_by_name'] ?? 'Cashier'}',
                    style: TextStyle(
                        color: context.labelColor,
                        fontSize: 18,
                        fontWeight: FontWeight.w800)),
              ),
              ReportBadge(
                text: '${_till['status']}',
                color: open
                    ? EnhancedTheme.accentOrange
                    : _varianceColor(_till['variance']),
              ),
            ]),
            const SizedBox(height: 12),
            _MoneyRow('Opening float', money(_till['opening_float'])),
            _MoneyRow('Cash taken', money(_till['cash_in'])),
            _MoneyRow('Change given', money(_till['change_out'])),
            const Divider(),
            _MoneyRow('Expected', money(_till['expected_amount']), bold: true),
            if (!open) ...[
              _MoneyRow('Counted', money(_till['counted_amount'])),
              _MoneyRow('Over / short', money(_till['variance']), bold: true),
            ],
            if ('${_till['notes'] ?? ''}'.trim().isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('${_till['notes']}',
                  style: TextStyle(color: context.hintColor, fontSize: 13)),
            ],
            const SizedBox(height: 16),
            if (open)
              FilledButton.icon(
                onPressed: _busy ? null : _close,
                icon: const Icon(Icons.lock_outline),
                label: const Text('Count and close'),
              ),
          ],
        ),
      ),
    );
  }
}

class _MoneyRow extends StatelessWidget {
  final String label;
  final String value;
  final bool bold;
  const _MoneyRow(this.label, this.value, {this.bold = false});

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
        color: bold ? context.labelColor : context.hintColor,
        fontSize: bold ? 15 : 13,
        fontWeight: bold ? FontWeight.w700 : FontWeight.w500);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: style),
        Text(value, style: style),
      ]),
    );
  }
}

class _OpenTillForm extends StatefulWidget {
  const _OpenTillForm();

  @override
  State<_OpenTillForm> createState() => _OpenTillFormState();
}

class _OpenTillFormState extends State<_OpenTillForm> {
  final _float = TextEditingController(text: '0');
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _float.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post(
          '/api/pharmacy/till-sessions/', {'opening_float': _float.text.trim()});
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: 'Open drawer',
      saving: _saving,
      error: _error,
      submitLabel: 'Open drawer',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _float,
          autofocus: true,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Opening float (₦)',
            helperText: 'Cash counted into the drawer before the first sale',
          ),
        ),
      ],
    );
  }
}
