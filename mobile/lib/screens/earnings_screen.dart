import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';

/// The prescriber's side of the ledger — GET /api/prescriptions/my-dues/.
///
/// What every pharmacy on the platform owes the signed-in prescriber for the
/// prescriptions it filled, matched by licence, and what has been paid. Read
/// with no facility picked: the API takes no tenant header here, so an
/// independent prescriber sees it before choosing where to write. The
/// pharmacy settles; this screen only reads.
class EarningsScreen extends StatefulWidget {
  const EarningsScreen({super.key});

  @override
  State<EarningsScreen> createState() => _EarningsScreenState();
}

class _EarningsScreenState extends State<EarningsScreen> {
  late Future<Map<String, dynamic>> _future = _load();

  Future<Map<String, dynamic>> _load() async =>
      ((await api.get('/api/prescriptions/my-dues/')) as Map)
          .cast<String, dynamic>();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return EmptyState(
            icon: Icons.account_balance_wallet_outlined,
            title: 'No statement',
            message: '${snap.error}',
            action: TextButton(
              onPressed: () => setState(() {
                _future = _load();
              }),
              child: const Text('Retry'),
            ),
          );
        }
        final s = snap.data ?? const {};
        final owed = (s['outstanding'] as Map?) ?? const {};
        final paid = (s['paid'] as Map?) ?? const {};
        final commissions = ((s['commissions'] ?? []) as List)
            .cast<Map<String, dynamic>>();
        final payouts = ((s['consultation_payouts'] ?? []) as List)
            .cast<Map<String, dynamic>>();
        return RefreshIndicator(
          onRefresh: () async {
            setState(() {
              _future = _load();
            });
            await _future;
          },
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Licence ${s['license_number'] ?? ''}',
                style: TextStyle(color: context.hintColor, fontSize: 12),
              ),
              const SizedBox(height: 4),
              Text(
                'A pharmacy that fills your prescription owes you its '
                'commission on the drugs and the fee for the consultation '
                'band you wrote — on its own terms with you.',
                style: TextStyle(color: context.hintColor, fontSize: 13),
              ),
              const SizedBox(height: 12),
              KpiRow(
                tiles: [
                  KpiTile(
                    icon: Icons.percent_outlined,
                    label: 'Commission owed',
                    value: money(owed['commission']),
                    color: EnhancedTheme.primaryTeal,
                  ),
                  KpiTile(
                    icon: Icons.medical_services_outlined,
                    label: 'Consultations owed',
                    value: money(owed['consultation']),
                    color: EnhancedTheme.accentCyan,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              KpiRow(
                tiles: [
                  KpiTile(
                    icon: Icons.account_balance_wallet_outlined,
                    label: 'Total owed',
                    value: money(owed['total']),
                    color: EnhancedTheme.accentOrange,
                  ),
                  KpiTile(
                    icon: Icons.check_circle_outline,
                    label: 'Paid to date',
                    value: money(paid['total']),
                    color: EnhancedTheme.successGreen,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (commissions.isEmpty && payouts.isEmpty)
                const EmptyState(
                  icon: Icons.receipt_long_outlined,
                  title: 'Nothing earned yet',
                  message:
                      'A pharmacy that has terms with you books what it '
                      'owes when it fills one of your prescriptions.',
                  boxed: true,
                ),
              if (commissions.isNotEmpty)
                _Ledger(
                  title: 'Commissions',
                  rows: [
                    for (final c in commissions)
                      _DueTile(
                        title:
                            '${c['pharmacy_name']} · ${c['commission_rate']}%',
                        amount: c['commission_amount'],
                        status: '${c['status']}',
                        when: '${c['created_at']}',
                        note:
                            c['order_name'] as String? ??
                            'on ${money(c['sales_amount'])} sold',
                      ),
                  ],
                ),
              if (payouts.isNotEmpty)
                _Ledger(
                  title: 'Consultation fees',
                  rows: [
                    for (final p in payouts)
                      _DueTile(
                        title:
                            '${p['pharmacy_name']} · band ${p['consultation_category']}',
                        amount: p['consultation_fee'],
                        status: '${p['status']}',
                        when: '${p['created_at']}',
                        note: p['order_name'] as String?,
                      ),
                  ],
                ),
            ],
          ),
        );
      },
    );
  }
}

class _Ledger extends StatelessWidget {
  final String title;
  final List<Widget> rows;
  const _Ledger({required this.title, required this.rows});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: TextStyle(
                color: context.labelColor,
                fontWeight: FontWeight.w700,
              ),
            ),
            ...rows,
          ],
        ),
      ),
    );
  }
}

class _DueTile extends StatelessWidget {
  final String title;
  final Object? amount;
  final String status;
  final String when;
  final String? note;
  const _DueTile({
    required this.title,
    required this.amount,
    required this.status,
    required this.when,
    this.note,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text(
        title,
        style: TextStyle(color: context.labelColor, fontSize: 14),
      ),
      subtitle: Text(
        [when.split('T').first, ?note].join(' · '),
        style: TextStyle(color: context.hintColor, fontSize: 12),
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            money(amount),
            style: TextStyle(
              color: context.labelColor,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
          Text(
            status,
            style: TextStyle(color: statusColor(status), fontSize: 11),
          ),
        ],
      ),
    );
  }
}
