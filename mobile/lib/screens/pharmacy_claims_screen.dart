import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_sales_screen.dart' show askAmount, askText;
import 'report_scaffold.dart';

/// HMO claims.
///
/// Staff submit; only the pharmacy admin approves, rejects or banks money —
/// the same split the API enforces, so a hidden button is convenience rather
/// than the control itself.
class PharmacyClaimsScreen extends StatelessWidget {
  const PharmacyClaimsScreen({super.key});

  @override
  Widget build(BuildContext context) => const _ClaimsTab();
}

Color _claimColor(String? status) => switch (status) {
      'paid' => EnhancedTheme.successGreen,
      'approved' => EnhancedTheme.infoBlue,
      'rejected' || 'cancelled' => EnhancedTheme.errorRed,
      'submitted' => EnhancedTheme.accentCyan,
      _ => EnhancedTheme.accentOrange,
    };

/// Runs one transition and reports what the API said. Every action here is a
/// POST to the claim's own endpoint, so the body is the only thing that varies.
Future<bool> _act(BuildContext context, String path,
    [Map<String, dynamic> body = const {}]) async {
  try {
    final r = await api.post(path, body);
    if (context.mounted) {
      showSuccess(context, '${(r as Map?)?['message'] ?? 'Done.'}');
    }
    return true;
  } catch (e) {
    if (context.mounted) showError(context, '$e');
    return false;
  }
}

class _ClaimsTab extends StatelessWidget {
  const _ClaimsTab();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) => ReportListScreen(
        path: '/api/pharmacy/claims/',
        searchHint: 'Search by claim or receipt number…',
        // Claims are raised by the sale that generated them — there is nothing
        // to add by hand here.
        fabLabel: 'Claim',
        showFab: false,
        emptyIcon: Icons.request_quote_outlined,
        emptyTitle: 'No claims yet',
        emptyMessage: 'An HMO sale raises its claim automatically.',
        savedMessage: '',
        filters: const [
          ReportFilter(param: 'status', anyLabel: 'Any status', options: {
            'draft': 'Draft',
            'submitted': 'Submitted',
            'approved': 'Approved',
            'rejected': 'Rejected',
            'paid': 'Paid',
            'cancelled': 'Cancelled',
          }),
        ],
        header: (items) => _ClaimsHeader(items: items),
        card: (row, reload, edit) =>
            _ClaimCard(row: row, role: snap.data, reload: reload),
        form: (_) => const SizedBox.shrink(),
      ),
    );
  }
}

class _ClaimsHeader extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _ClaimsHeader({required this.items});

  @override
  Widget build(BuildContext context) {
    final live = items.where((r) => r['status'] != 'cancelled');
    num sum(String key) => live.fold<num>(
        0, (total, r) => total + (num.tryParse('${r[key]}') ?? 0));
    final outstanding = sum('amount_approved') - sum('amount_paid');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.request_quote_outlined,
          title: 'Claims',
          subtitle: '${items.length} listed',
          color: EnhancedTheme.accentCyan,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.upload_file_outlined,
              label: 'Claimed',
              value: money(sum('amount')),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.verified_outlined,
              label: 'Approved',
              value: money(sum('amount_approved')),
              color: EnhancedTheme.infoBlue),
          KpiTile(
              icon: Icons.hourglass_bottom,
              label: 'Outstanding',
              value: money(outstanding < 0 ? 0 : outstanding),
              color: EnhancedTheme.accentOrange),
        ]),
      ]),
    );
  }
}

class _ClaimCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final String? role;
  final VoidCallback reload;
  const _ClaimCard({required this.row, required this.role, required this.reload});

  Future<void> _run(BuildContext context, String action) async {
    final id = row['id'];
    Map<String, dynamic> body = const {};
    if (action == 'approve') {
      final amount = await askAmount(context, 'Approve claim',
          'Approved amount (₦)', '${row['amount']}');
      if (amount == null || !context.mounted) return;
      body = {'amount': amount};
    } else if (action == 'reject') {
      final reason = await askText(context, 'Reject claim', 'Reason');
      if (reason == null || !context.mounted) return;
      body = {'reason': reason};
    } else if (action == 'pay') {
      final amount = await askAmount(
          context, 'Record payment', 'Amount (₦)', '${row['outstanding']}');
      if (amount == null || !context.mounted) return;
      body = {'amount': amount};
    }
    if (await _act(context, '/api/pharmacy/claims/$id/$action/', body)) {
      reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    final actions = claimActions('${row['status']}', role);
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['hmo_name'] ?? 'Claim'} · ${row['reference']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: _claimColor('${row['status']}')),
        ]),
        const SizedBox(height: 6),
        Text(
          [
            'Receipt ${row['sale_reference'] ?? '—'}',
            if ((row['patient_name'] ?? '').toString().isNotEmpty)
              '${row['patient_name']}',
            if ((row['enrollment_member_number'] ?? '').toString().isNotEmpty)
              'Card ${row['enrollment_member_number']}',
          ].join(' · '),
          style: TextStyle(color: context.hintColor, fontSize: 13),
        ),
        const SizedBox(height: 4),
        Text(
          'Claimed ${money(row['amount'])}'
          ' · approved ${money(row['amount_approved'])}'
          ' · paid ${money(row['amount_paid'])}',
          style: const TextStyle(
              color: EnhancedTheme.primaryTeal, fontWeight: FontWeight.w700),
        ),
        if (actions.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(spacing: 8, children: [
            for (final a in actions)
              OutlinedButton(
                onPressed: () => _run(context, a),
                child: Text(a == 'pay' ? 'Record payment' : _title(a)),
              ),
          ]),
        ],
      ]),
    );
  }
}

String _title(String action) =>
    action[0].toUpperCase() + action.substring(1).replaceAll('-', ' ');
