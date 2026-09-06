import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_sales_screen.dart' show askText;
import 'report_scaffold.dart';

/// Clearances asked of an insurer before a high-value covered sale.
///
/// Requests are raised at the counter, with the basket in front of the
/// pharmacist — there is nothing to add by hand here. What this screen is for
/// is the answer: the admin records what the insurer said, and everyone sees
/// it, because a cleared quantity is what the counter may dispense.
class PharmacyPreauthScreen extends StatelessWidget {
  const PharmacyPreauthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) => ReportListScreen(
        path: '/api/pharmacy/pre-authorizations/',
        searchHint: 'Search by reference or insurer code…',
        fabLabel: 'Request',
        // Raised from the dispensing counter, against a priced basket.
        showFab: false,
        emptyIcon: Icons.verified_user_outlined,
        emptyTitle: 'No authorisation requests',
        emptyMessage: 'Ask the insurer from the dispensing counter, where the '
            'basket is already priced.',
        savedMessage: '',
        filters: const [
          ReportFilter(param: 'status', anyLabel: 'Any status', options: {
            'requested': 'Awaiting the insurer',
            'approved': 'Approved',
            'declined': 'Declined',
            'used': 'Used',
            'cancelled': 'Withdrawn',
          }),
        ],
        header: (items) => _PreauthHeader(items: items),
        card: (row, reload, edit) =>
            _PreauthCard(row: row, role: snap.data, reload: reload),
        form: (_) => const SizedBox.shrink(),
      ),
    );
  }
}

Color _authColor(String? status) => switch (status) {
      'approved' => EnhancedTheme.successGreen,
      'used' => EnhancedTheme.infoBlue,
      'declined' || 'cancelled' => EnhancedTheme.errorRed,
      _ => EnhancedTheme.accentOrange,
    };

/// Runs one decision and reports what the API said.
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

class _PreauthHeader extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _PreauthHeader({required this.items});

  @override
  Widget build(BuildContext context) {
    num sum(Iterable<Map<String, dynamic>> rows, String key) =>
        rows.fold<num>(0, (total, r) => total + (num.tryParse('${r[key]}') ?? 0));
    final waiting = items.where((r) => r['status'] == 'requested');
    final usable = items.where((r) => r['is_usable'] == true);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.verified_user_outlined,
          title: 'Authorisations',
          subtitle: '${items.length} listed',
          color: EnhancedTheme.accentCyan,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.hourglass_bottom,
              label: 'Awaiting',
              value: units(waiting.length),
              color: EnhancedTheme.accentOrange),
          KpiTile(
              icon: Icons.upload_file_outlined,
              label: 'Asked',
              value: money(sum(items, 'amount')),
              color: EnhancedTheme.primaryTeal),
          KpiTile(
              icon: Icons.verified_outlined,
              label: 'Usable',
              value: money(sum(usable, 'amount_approved')),
              color: EnhancedTheme.successGreen),
        ]),
      ]),
    );
  }
}

class _PreauthCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final String? role;
  final VoidCallback reload;
  const _PreauthCard(
      {required this.row, required this.role, required this.reload});

  List<Map<String, dynamic>> get _items =>
      ((row['items'] ?? const []) as List).cast<Map<String, dynamic>>();

  /// The insurer's answer to the request as a whole. Only offered on a
  /// lump-sum request: an itemised one settles itself from its medications.
  Future<void> _run(BuildContext context, String action) async {
    Map<String, dynamic> body = const {};
    if (action == 'approve') {
      final decision = await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (_) => _ApproveDialog(
            title: "Record the insurer's answer", asked: '${row['amount']}'),
      );
      if (decision == null || !context.mounted) return;
      body = decision;
    } else {
      final reason = await askText(
          context,
          switch (action) {
            'decline' => 'Decline request',
            'reopen' => 'Reopen request',
            _ => 'Withdraw request',
          },
          'Reason');
      if (reason == null || !context.mounted) return;
      body = {'reason': reason};
    }
    if (await _act(context, '/api/pharmacy/pre-authorizations/'
        '${row['id']}/$action/', body)) {
      reload();
    }
  }

  /// The insurer's answer to one ordered medication.
  Future<void> _decide(
      BuildContext context, Map<String, dynamic> line, String action) async {
    Map<String, dynamic> body = const {};
    if (action == 'approve') {
      final decision = await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (_) => _ApproveDialog(
          title: 'Authorise ${line['item_name'] ?? 'medication'}',
          asked: '${line['amount']}',
          maxQuantity: (line['quantity'] as num?)?.toInt() ?? 1,
        ),
      );
      if (decision == null || !context.mounted) return;
      body = decision;
    } else {
      final reason = await askText(
          context,
          action == 'reopen' ? 'Reopen medication' : 'Decline medication',
          'Reason');
      if (reason == null || !context.mounted) return;
      body = {'reason': reason};
    }
    if (await _act(context, '/api/pharmacy/pre-authorization-items/'
        '${line['id']}/$action/', body)) {
      reload();
    }
  }

  /// What the insurer said about one medication, in the counter's words.
  String _answer(Map<String, dynamic> line) {
    final reason = '${line['reason'] ?? ''}';
    return switch ('${line['status']}') {
      'approved' => 'Cleared ${line['quantity_approved']}'
          ' · ${money(line['amount_approved'])}',
      'declined' => 'Declined${reason.isEmpty ? '' : ' · $reason'}',
      _ => 'Awaiting the insurer',
    };
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    final status = '${row['status']}';
    final decidesItems = isPharmacyAdmin(role) && status == 'requested';
    // A wrong answer to a medication is undone until the clearance is spent.
    final reopensItems =
        isPharmacyAdmin(role) && status != 'used' && status != 'cancelled';
    final actions = preauthActions(status, role, itemised: items.isNotEmpty);
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['hmo_name'] ?? 'Request'} · ${row['reference']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          ReportBadge(text: status, color: _authColor(status)),
        ]),
        const SizedBox(height: 6),
        Text(
          [
            if ('${row['patient_name'] ?? ''}'.isNotEmpty) '${row['patient_name']}',
            if ('${row['member_number'] ?? ''}'.isNotEmpty)
              'Card ${row['member_number']}',
            if ('${row['code'] ?? ''}'.isNotEmpty) 'Code ${row['code']}',
            if (row['expires_on'] != null) 'Expires ${row['expires_on']}',
            // An answer withdrawn more than once is worth a second look
            // before the insurer is billed against it.
            if ((row['reopened_count'] as num? ?? 0) > 0)
              'Reopened ${row['reopened_count']}×',
            if ('${row['sale_reference'] ?? ''}'.isNotEmpty)
              'Spent on ${row['sale_reference']}',
          ].join(' · '),
          style: TextStyle(color: context.hintColor, fontSize: 13),
        ),
        const SizedBox(height: 4),
        Text(
          'Asked ${money(row['amount'])}'
          ' · authorised ${money(row['amount_approved'])}',
          style: const TextStyle(
              color: EnhancedTheme.primaryTeal, fontWeight: FontWeight.w700),
        ),
        if ('${row['reason'] ?? ''}'.isNotEmpty)
          Text('${row['reason']}',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
        if (items.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Ordered medications',
              style: TextStyle(
                  color: context.labelColor,
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
          for (final line in items)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child:
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${line['quantity']} × ${line['item_name'] ?? line['item']}'
                    ' · ${money(line['amount'])}',
                    style:
                        TextStyle(color: context.labelColor, fontSize: 13)),
                Text(_answer(line),
                    style: TextStyle(color: context.hintColor, fontSize: 12)),
                if (decidesItems && line['status'] == 'requested')
                  Wrap(spacing: 8, children: [
                    OutlinedButton(
                        onPressed: () => _decide(context, line, 'approve'),
                        child: const Text('Approve')),
                    OutlinedButton(
                        onPressed: () => _decide(context, line, 'decline'),
                        child: const Text('Decline')),
                  ])
                else if (reopensItems && line['status'] != 'requested')
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton(
                        onPressed: () => _decide(context, line, 'reopen'),
                        child: const Text('Reopen')),
                  ),
              ]),
            ),
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(
                'The insurer answers each medication on its own and may clear '
                'less than was asked. The counter dispenses up to the quantity '
                'cleared; a declined medication is refused at the till.',
                style: TextStyle(color: context.hintColor, fontSize: 12)),
          ),
        ],
        if (actions.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(spacing: 8, children: [
            for (final a in actions)
              OutlinedButton(
                onPressed: () => _run(context, a),
                child: Text(a == 'cancel' ? 'Withdraw' : _title(a)),
              ),
          ]),
        ],
      ]),
    );
  }
}

String _title(String action) => action[0].toUpperCase() + action.substring(1);

/// What the insurer stood behind: an amount, and — for one medication — the
/// quantity they cleared.
///
/// Every field is optional. Left blank, the API stands behind the whole ask,
/// and a cut quantity with no amount typed bills pro rata server-side.
class _ApproveDialog extends StatefulWidget {
  final String title;
  final String asked;
  /// Set for one medication: how many units were asked for, the ceiling on
  /// what the insurer can clear. Null for a lump-sum request, which instead
  /// carries the insurer's code and an expiry.
  final int? maxQuantity;

  const _ApproveDialog(
      {required this.title, required this.asked, this.maxQuantity});

  @override
  State<_ApproveDialog> createState() => _ApproveDialogState();
}

class _ApproveDialogState extends State<_ApproveDialog> {
  late final _quantity =
      TextEditingController(text: '${widget.maxQuantity ?? ''}');
  final _amount = TextEditingController();
  final _code = TextEditingController();
  DateTime? _expires;
  String? _error;

  @override
  void dispose() {
    _quantity.dispose();
    _amount.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _pickExpiry() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _expires ?? now,
      firstDate: now,
      lastDate: DateTime(now.year + 3),
    );
    if (picked != null) setState(() => _expires = picked);
  }

  void _submit() {
    final body = <String, dynamic>{};
    final max = widget.maxQuantity;
    if (max != null) {
      final cleared = int.tryParse(_quantity.text.trim()) ?? 0;
      if (cleared < 1 || cleared > max) {
        setState(() => _error = 'The insurer can clear 1 to $max of that.');
        return;
      }
      body['quantity'] = cleared;
    }
    final amount = _amount.text.trim();
    if (amount.isNotEmpty) {
      if ((double.tryParse(amount) ?? 0) <= 0) {
        setState(() => _error = 'An authorised amount must be positive.');
        return;
      }
      body['amount'] = amount;
    }
    if (max == null) {
      if (_code.text.trim().isNotEmpty) body['code'] = _code.text.trim();
      if (_expires != null) {
        body['expires_on'] = _expires!.toIso8601String().substring(0, 10);
      }
    }
    Navigator.of(context).pop(body);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (widget.maxQuantity != null)
            TextField(
              controller: _quantity,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                labelText: 'Quantity authorised',
                helperText: '${widget.maxQuantity} asked for',
              ),
            ),
          TextField(
            controller: _amount,
            keyboardType: TextInputType.number,
            decoration: InputDecoration(
              labelText: 'Amount authorised (₦)',
              hintText: widget.asked,
              helperText: 'Blank stands behind ${money(widget.asked)}.',
            ),
          ),
          if (widget.maxQuantity == null) ...[
            TextField(
              controller: _code,
              decoration:
                  const InputDecoration(labelText: "The insurer's code"),
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Expires on'),
              subtitle: Text(_expires == null
                  ? 'Does not lapse'
                  : _expires!.toIso8601String().substring(0, 10)),
              trailing: const Icon(Icons.event_outlined),
              onTap: _pickExpiry,
            ),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!,
                  style: const TextStyle(color: EnhancedTheme.errorRed)),
            ),
        ]),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Back')),
        FilledButton(onPressed: _submit, child: const Text('Authorise')),
      ],
    );
  }
}
