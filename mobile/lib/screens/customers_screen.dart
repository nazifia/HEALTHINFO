import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Customers — GET /api/customers/.
///
/// The counter's record of who buys, and the prepaid money they hold with the
/// pharmacy. Deliberately not a patient: most people who buy paracetamol are
/// neither registered nor examined. Where the two are the same person, the
/// form links them.
///
/// The wallet is never edited here. It moves through top-up, deduct and the
/// sale that spends it, each of which writes a ledger row somebody can point
/// at — so the balance on the card is always explained.
class CustomersScreen extends StatelessWidget {
  const CustomersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final role = snap.data;
        return ReportListScreen(
          path: '/api/customers/',
          searchHint: 'Name, phone or email…',
          fabLabel: 'Add customer',
          showFab: isPharmacyStaff(role),
          emptyIcon: Icons.people_alt_outlined,
          emptyTitle: 'No customers yet',
          emptyMessage:
              'Tap "Add customer" — a phone number is what finds them again.',
          savedMessage: 'Customer saved.',
          filters: const [
            ReportFilter(param: 'is_wholesale', anyLabel: 'Any type', options: {
              'false': 'Retail',
              'true': 'Wholesale',
            }),
            ReportFilter(param: 'ordering', anyLabel: 'By name', options: {
              '-outstanding_debt': 'Owing most',
              '-wallet_balance': 'Biggest wallet',
              '-created_at': 'Newest',
            }),
          ],
          header: (items) => const _Header(),
          card: (row, reload, edit) => _CustomerCard(row: row, edit: edit),
          onTap: (row) => _openWallet(context, row, role),
          form: (existing) => _CustomerForm(existing: existing),
        );
      },
    );
  }

  static Future<void> _openWallet(
      BuildContext context, Map<String, dynamic> row, String? role) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => WalletSheet(customer: row, role: role),
    );
  }
}

/// KPI strip from /api/customers/summary/ — the server totals the wallets, so
/// the header is right even when the list below is filtered or paginated.
class _Header extends StatefulWidget {
  const _Header();

  @override
  State<_Header> createState() => _HeaderState();
}

class _HeaderState extends State<_Header> {
  late final Future<dynamic> _future = api.get('/api/customers/summary/');

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<dynamic>(
      future: _future,
      builder: (context, snap) {
        final s = (snap.data as Map?)?.cast<String, dynamic>() ?? const {};
        return Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Column(children: [
            StatsHeader(
              icon: Icons.people_alt_outlined,
              title: 'Customers',
              subtitle: '${units(s['retail'])} retail · '
                  '${units(s['wholesale'])} wholesale',
              color: EnhancedTheme.primaryTeal,
            ),
            KpiRow(tiles: [
              KpiTile(
                  icon: Icons.groups_outlined,
                  label: 'On the books',
                  value: units(s['total']),
                  color: EnhancedTheme.primaryTeal),
              KpiTile(
                  icon: Icons.account_balance_wallet_outlined,
                  label: 'Wallets hold',
                  value: money(s['wallet_balance']),
                  color: EnhancedTheme.accentCyan),
              KpiTile(
                  icon: Icons.money_off_outlined,
                  label: 'Owed to us',
                  value: money(s['outstanding_debt']),
                  color: EnhancedTheme.accentOrange),
            ]),
          ]),
        );
      },
    );
  }
}

class _CustomerCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback edit;
  const _CustomerCard({required this.row, required this.edit});

  @override
  Widget build(BuildContext context) {
    final debt = num.tryParse('${row['outstanding_debt']}') ?? 0;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['name']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          if (row['is_wholesale'] == true)
            const ReportBadge(
                text: 'wholesale', color: EnhancedTheme.accentCyan),
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
        ]),
        Text('${row['phone'] ?? ''}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        const SizedBox(height: 6),
        Row(children: [
          Expanded(
            child: Text('Wallet ${money(row['wallet_balance'])}',
                style: const TextStyle(
                    color: EnhancedTheme.successGreen,
                    fontSize: 13,
                    fontWeight: FontWeight.w700)),
          ),
          if (debt > 0)
            Text('Owes ${money(debt)}',
                style: const TextStyle(
                    color: EnhancedTheme.errorRed,
                    fontSize: 13,
                    fontWeight: FontWeight.w700)),
        ]),
        if (row['total_purchases'] != null)
          Text('Spent ${money(row['total_purchases'])} to date',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
      ]),
    );
  }
}

/// One wallet: the balance, the debt, and every row that explains them.
class WalletSheet extends StatefulWidget {
  final Map<String, dynamic> customer;
  final String? role;
  const WalletSheet({super.key, required this.customer, this.role});

  @override
  State<WalletSheet> createState() => _WalletSheetState();
}

class _WalletSheetState extends State<WalletSheet> {
  late Future<dynamic> _future = _load();
  bool _busy = false;

  int get _id => widget.customer['id'] as int;

  Future<dynamic> _load() => api.get('/api/customers/$_id/wallet/');

  Future<void> _refresh() async {
    final f = _load();
    setState(() => _future = f);
    await f;
  }

  Future<void> _move(String action) async {
    final topUp = action == 'top-up';
    final amount = await _askWallet(context, topUp);
    if (amount == null || !mounted) return;
    setState(() => _busy = true);
    await runAction(context, '/api/customers/$_id/$action/',
        body: walletBody(amount.value,
            method: amount.method, note: amount.note, topUp: topUp),
        after: _refresh);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    // Only the admin may take money off a wallet outright: that is a
    // correction, and a correction that moves money needs an owner.
    final actions = [
      'top-up',
      if (isPharmacyAdmin(widget.role)) 'deduct',
    ];
    return Container(
      constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.85),
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: FutureBuilder<dynamic>(
        future: _future,
        builder: (context, snap) {
          final w = (snap.data as Map?)?.cast<String, dynamic>() ?? const {};
          final rows = ((w['transactions'] ?? []) as List)
              .cast<Map<String, dynamic>>();
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${widget.customer['name']}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
              Text('${widget.customer['phone'] ?? ''}',
                  style: TextStyle(color: context.hintColor, fontSize: 13)),
              const SizedBox(height: 12),
              FactRow('Wallet balance', money(w['balance']), bold: true),
              FactRow('Outstanding debt', money(w['outstanding_debt'])),
              // Paying in while you owe pays the debt off first — the sheet
              // says so, because the balance afterwards will not be the sum
              // somebody expects otherwise.
              Text('A top-up clears the debt before it adds credit.',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
              if (_busy)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: LinearProgressIndicator(minHeight: 2),
                )
              else
                ActionRow(actions: actions, onAction: _move),
              const Divider(),
              Text('Ledger',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 15,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Flexible(
                child: snap.connectionState == ConnectionState.waiting
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.all(24),
                          child: CircularProgressIndicator(
                              color: EnhancedTheme.primaryTeal),
                        ),
                      )
                    : rows.isEmpty
                        ? const EmptyState(
                            icon: Icons.receipt_long_outlined,
                            title: 'Nothing on the wallet yet',
                            message: 'Top it up and the rows appear here.',
                          )
                        : ListView.builder(
                            shrinkWrap: true,
                            itemCount: rows.length,
                            itemBuilder: (context, i) {
                              final t = rows[i];
                              final kind = '${t['txn_type']}';
                              final out = kind != 'topup';
                              return ListTile(
                                dense: true,
                                contentPadding: EdgeInsets.zero,
                                title: Text(
                                  '${out ? '−' : '+'}${money(t['amount'])}',
                                  style: TextStyle(
                                      color: out
                                          ? EnhancedTheme.errorRed
                                          : EnhancedTheme.successGreen,
                                      fontWeight: FontWeight.w700,
                                      fontSize: 14),
                                ),
                                subtitle: Text(
                                  [
                                    kind,
                                    if ('${t['method'] ?? ''}'.isNotEmpty)
                                      '${t['method']}',
                                    if ('${t['note'] ?? ''}'.isNotEmpty)
                                      '${t['note']}',
                                    '${t['created_at']}'.split('T').first,
                                  ].join(' · '),
                                  style: TextStyle(
                                      color: context.hintColor, fontSize: 12),
                                ),
                              );
                            },
                          ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// What a wallet movement carries: the amount, how the cash arrived, and why.
typedef _WalletInput = ({String value, String method, String note});

Future<_WalletInput?> _askWallet(BuildContext context, bool topUp) {
  final amount = TextEditingController();
  final note = TextEditingController();
  var method = 'cash';
  return showDialog<_WalletInput>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, setState) => AlertDialog(
        title: Text(topUp ? 'Top up wallet' : 'Deduct from wallet'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: amount,
            autofocus: true,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Amount (₦)'),
          ),
          if (topUp) ...[
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              initialValue: method,
              decoration: const InputDecoration(labelText: 'Paid by'),
              items: const [
                DropdownMenuItem(value: 'cash', child: Text('Cash')),
                DropdownMenuItem(value: 'pos', child: Text('POS / card')),
                DropdownMenuItem(value: 'transfer', child: Text('Transfer')),
              ],
              onChanged: (v) => setState(() => method = v ?? 'cash'),
            ),
          ],
          const SizedBox(height: 8),
          TextField(
            controller: note,
            decoration: const InputDecoration(labelText: 'Note (optional)'),
          ),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              final v = amount.text.trim();
              if (v.isEmpty) return;
              Navigator.of(context)
                  .pop((value: v, method: method, note: note.text.trim()));
            },
            child: Text(topUp ? 'Top up' : 'Deduct'),
          ),
        ],
      ),
    ),
  );
}

class _CustomerForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _CustomerForm({this.existing});

  @override
  State<_CustomerForm> createState() => _CustomerFormState();
}

class _CustomerFormState extends State<_CustomerForm> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _address = TextEditingController();
  bool _wholesale = false;
  bool _active = true;
  int? _patientId;
  String? _patientLabel;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _name.text = '${e['name'] ?? ''}';
      _phone.text = '${e['phone'] ?? ''}';
      _email.text = '${e['email'] ?? ''}';
      _address.text = '${e['address'] ?? ''}';
      _wholesale = e['is_wholesale'] == true;
      _active = e['is_active'] == true;
      _patientId = e['patient'] as int?;
      _patientLabel = e['patient_name'] as String?;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _email.dispose();
    _address.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty || _phone.text.trim().isEmpty) {
      setState(() => _error = 'A name and a phone number identify a customer.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim(),
        'address': _address.text.trim(),
        'is_wholesale': _wholesale,
        'is_active': _active,
        'patient': _patientId,
      };
      if (_isEdit) {
        await api.patch('/api/customers/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/customers/', body);
      }
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
      title: _isEdit ? 'Edit customer' : 'New customer',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add customer',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            labelText: 'Phone',
            helperText: 'One per customer — it is what finds them on a return',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: 'Email (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _address,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Address (optional)'),
        ),
        const SizedBox(height: 12),
        // Linking a patient is how insurance and clinical history reach this
        // buyer; without it they are just a name at the counter.
        PatientPicker(
          initialId: _patientId,
          initialLabel: _patientLabel,
          onChanged: (id) => _patientId = id,
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Wholesale'),
          subtitle: const Text('Buys packs from the wholesale counter'),
          value: _wholesale,
          onChanged: (v) => setState(() => _wholesale = v),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Active'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
      ],
    );
  }
}
