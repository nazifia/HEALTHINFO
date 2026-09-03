import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_sales_screen.dart' show askAmount, askText;
import 'report_scaffold.dart';

/// HMO claims and the monthly schedules they are sent in.
///
/// Staff submit; only the pharmacy admin approves, rejects or banks money —
/// the same split the API enforces, so a hidden button is convenience rather
/// than the control itself.
class PharmacyClaimsScreen extends StatelessWidget {
  const PharmacyClaimsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(children: [
        const TabBar(
          labelColor: EnhancedTheme.primaryTeal,
          indicatorColor: EnhancedTheme.primaryTeal,
          tabs: [Tab(text: 'Claims'), Tab(text: 'Batches')],
        ),
        const Expanded(
          child: TabBarView(children: [_ClaimsTab(), _BatchesTab()]),
        ),
      ]),
    );
  }
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
            if ((row['batch_reference'] ?? '').toString().isNotEmpty)
              'Schedule ${row['batch_reference']}',
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

class _BatchesTab extends StatelessWidget {
  const _BatchesTab();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) => ReportListScreen(
        path: '/api/pharmacy/claim-batches/',
        fabLabel: 'New batch',
        showFab: isPharmacyStaff(snap.data),
        emptyIcon: Icons.folder_copy_outlined,
        emptyTitle: 'No claim batches yet',
        emptyMessage:
            'Bundle a month of claims for one insurer into a single schedule.',
        savedMessage: 'Batch created.',
        filters: const [
          ReportFilter(param: 'status', anyLabel: 'Any status', options: {
            'draft': 'Draft',
            'submitted': 'Submitted',
            'approved': 'Approved',
            'paid': 'Paid',
            'cancelled': 'Cancelled',
          }),
        ],
        card: (row, reload, edit) =>
            _BatchCard(row: row, role: snap.data, reload: reload),
        form: (_) => const _BatchForm(),
      ),
    );
  }
}

class _BatchCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final String? role;
  final VoidCallback reload;
  const _BatchCard({required this.row, required this.role, required this.reload});

  Future<void> _run(BuildContext context, String action) async {
    Map<String, dynamic> body = const {};
    if (action == 'pay') {
      final totals = (row['totals'] as Map?) ?? const {};
      final amount = await askAmount(context, 'Allocate remittance',
          'Amount (₦)', '${totals['outstanding'] ?? ''}');
      if (amount == null || !context.mounted) return;
      body = {'amount': amount};
    }
    if (await _act(
        context, '/api/pharmacy/claim-batches/${row['id']}/$action/', body)) {
      reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    final totals = (row['totals'] as Map?) ?? const {};
    final actions = batchActions('${row['status']}', role);
    final period = [row['period_start'], row['period_end']]
        .where((d) => d != null)
        .join(' → ');
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['hmo_name'] ?? 'Batch'} · ${row['reference']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(
              text: '${row['status']}', color: _claimColor('${row['status']}')),
        ]),
        if (period.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(period, style: TextStyle(color: context.hintColor, fontSize: 13)),
        ],
        const SizedBox(height: 4),
        Text(
          '${totals['claims'] ?? 0} claim(s)'
          ' · ${money(totals['claimed'])} claimed'
          ' · ${money(totals['outstanding'])} outstanding',
          style: const TextStyle(
              color: EnhancedTheme.primaryTeal, fontWeight: FontWeight.w700),
        ),
        if (actions.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(spacing: 8, children: [
            for (final a in actions)
              OutlinedButton(
                onPressed: () => _run(context, a),
                child: Text(a == 'pay' ? 'Allocate remittance' : _title(a)),
              ),
          ]),
        ],
      ]),
    );
  }
}

/// A new schedule. Creating it collects the insurer's unbatched open claims for
/// the period, which is the whole job most months.
class _BatchForm extends StatefulWidget {
  const _BatchForm();

  @override
  State<_BatchForm> createState() => _BatchFormState();
}

class _BatchFormState extends State<_BatchForm> {
  List<Map<String, dynamic>> _hmos = [];
  int? _hmoId;
  DateTime? _from;
  DateTime? _to;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = DateTime(now.year, now.month, 1);
    _to = now;
    _loadHmos();
  }

  Future<void> _loadHmos() async {
    try {
      final rows = await api.getList('/api/pharmacy/hmos/', {'is_active': 'true'});
      if (mounted) setState(() => _hmos = rows.cast<Map<String, dynamic>>());
    } catch (_) {
      // The submit still validates; an empty picker just says pick an insurer.
    }
  }

  Future<void> _pick(bool isFrom) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: (isFrom ? _from : _to) ?? now,
      firstDate: DateTime(now.year - 3),
      lastDate: DateTime(now.year + 1),
    );
    if (picked == null) return;
    setState(() => isFrom ? _from = picked : _to = picked);
  }

  String _fmt(DateTime? d) =>
      d == null ? 'Not set' : d.toIso8601String().substring(0, 10);

  Future<void> _submit() async {
    if (_hmoId == null) {
      setState(() => _error = 'Pick the insurer.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.post('/api/pharmacy/claim-batches/', {
        'hmo': _hmoId,
        if (_from != null) 'period_start': _fmt(_from),
        if (_to != null) 'period_end': _fmt(_to),
      });
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
      title: 'New claim batch',
      saving: _saving,
      error: _error,
      submitLabel: 'Create and collect',
      onSubmit: _submit,
      children: [
        SearchableDropdown<int?>(
          initialValue: _hmoId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Insurer'),
          items: [
            const DropdownMenuItem(value: null, child: Text('— select —')),
            for (final h in _hmos)
              DropdownMenuItem(value: h['id'] as int, child: Text('${h['name']}')),
          ],
          onChanged: (v) => setState(() => _hmoId = v),
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Period from'),
          subtitle: Text(_fmt(_from)),
          trailing: const Icon(Icons.event_outlined),
          onTap: () => _pick(true),
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Period to'),
          subtitle: Text(_fmt(_to)),
          trailing: const Icon(Icons.event_outlined),
          onTap: () => _pick(false),
        ),
      ],
    );
  }
}
