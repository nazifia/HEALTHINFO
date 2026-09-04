import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Prescribers — GET /api/prescriptions/prescribers/.
///
/// Doctors whose scripts this pharmacy fills, and the two kinds of money that
/// flow back to them: a commission on what their script sold, and the flat
/// consultation fee charged at the till and owed on in full. Both are
/// snapshotted when raised, so repricing a drug or a rate tomorrow cannot
/// rewrite what was earned today.
///
/// Rates and bands are money policy, so writing them is the admin's; every
/// dispenser reads the list. Settling is the admin's too — it is the
/// pharmacy's money going out.
class PrescribersScreen extends StatelessWidget {
  const PrescribersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return ReportListScreen(
          path: '/api/prescriptions/prescribers/',
          searchHint: 'Name, licence, specialty or clinic…',
          fabLabel: 'Add prescriber',
          showFab: admin,
          emptyIcon: Icons.badge_outlined,
          emptyTitle: 'No prescribers yet',
          emptyMessage: admin
              ? 'Add the doctors whose scripts you fill.'
              : 'The pharmacy admin keeps the prescriber list.',
          savedMessage: 'Prescriber saved.',
          filters: const [
            ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
              'true': 'Active',
              'false': 'Retired',
            }),
            ReportFilter(param: 'is_verified', anyLabel: 'Any', options: {
              'true': 'Verified',
              'false': 'Unverified',
            }),
          ],
          card: (row, reload, edit) =>
              _PrescriberCard(row: row, admin: admin, edit: edit),
          onTap: (row) => _statement(context, row, admin),
          form: (existing) => _PrescriberForm(existing: existing),
        );
      },
    );
  }

  static Future<void> _statement(
      BuildContext context, Map<String, dynamic> row, bool admin) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => StatementSheet(prescriber: row, admin: admin),
    );
  }
}

class _PrescriberCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _PrescriberCard(
      {required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    final owed = (row['outstanding'] as Map?)?['total'];
    final where = [
      '${row['hospital_name'] ?? row['clinic'] ?? ''}',
      '${row['specialty'] ?? ''}',
    ].where((v) => v.trim().isNotEmpty).join(' · ');
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
          if (row['is_verified'] == true)
            const Icon(Icons.verified_outlined,
                size: 18, color: EnhancedTheme.successGreen),
          if (row['is_active'] != true) ...[
            const SizedBox(width: 6),
            const ReportBadge(text: 'retired', color: EnhancedTheme.errorRed),
          ],
          if (admin)
            IconButton(
                icon: const Icon(Icons.edit_outlined, size: 18),
                onPressed: edit),
        ]),
        if (where.isNotEmpty)
          Text(where, style: TextStyle(color: context.hintColor, fontSize: 13)),
        const SizedBox(height: 6),
        Text('${row['commission_rate']}% commission',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if ((num.tryParse('$owed') ?? 0) > 0)
          Text('Owed ${money(owed)}',
              style: const TextStyle(
                  color: EnhancedTheme.accentOrange,
                  fontSize: 13,
                  fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

/// What a prescriber has earned, and the button that settles it.
class StatementSheet extends StatefulWidget {
  final Map<String, dynamic> prescriber;
  final bool admin;
  const StatementSheet(
      {super.key, required this.prescriber, required this.admin});

  @override
  State<StatementSheet> createState() => _StatementSheetState();
}

class _StatementSheetState extends State<StatementSheet> {
  late Future<dynamic> _future = _load();
  bool _busy = false;

  int get _id => widget.prescriber['id'] as int;

  Future<dynamic> _load() =>
      api.get('/api/prescriptions/prescribers/$_id/statement/');

  Future<void> _refresh() async {
    final f = _load();
    setState(() => _future = f);
    await f;
  }

  /// Settle everything still pending for this prescriber, in one call per
  /// kind — commissions and consultation fees are separate ledgers.
  Future<void> _payAll() async {
    setState(() => _busy = true);
    final ok = await runAction(
        context, '/api/prescriptions/commissions/pay-all/',
        body: {'prescriber': _id});
    if (ok && mounted) {
      await runAction(
          context, '/api/prescriptions/consultation-payouts/pay-all/',
          body: {'prescriber': _id}, after: _refresh);
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints:
          BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: FutureBuilder<dynamic>(
        future: _future,
        builder: (context, snap) {
          final s = (snap.data as Map?)?.cast<String, dynamic>() ?? const {};
          final owed = (s['outstanding'] as Map?) ?? const {};
          final commissions =
              ((s['commissions'] ?? []) as List).cast<Map<String, dynamic>>();
          final payouts = ((s['consultation_payouts'] ?? []) as List)
              .cast<Map<String, dynamic>>();
          final pending = (num.tryParse('${owed['total']}') ?? 0) > 0;
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${widget.prescriber['name']}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
              const SizedBox(height: 12),
              KpiRow(tiles: [
                KpiTile(
                    icon: Icons.percent_outlined,
                    label: 'Commission due',
                    value: money(owed['commission']),
                    color: EnhancedTheme.primaryTeal),
                KpiTile(
                    icon: Icons.medical_services_outlined,
                    label: 'Consultations due',
                    value: money(owed['consultation']),
                    color: EnhancedTheme.accentCyan),
                KpiTile(
                    icon: Icons.account_balance_wallet_outlined,
                    label: 'Total owed',
                    value: money(owed['total']),
                    color: EnhancedTheme.accentOrange),
              ]),
              if (_busy)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: LinearProgressIndicator(minHeight: 2),
                )
              else if (widget.admin && pending)
                ActionRow(actions: const ['pay-all'], onAction: (_) => _payAll()),
              const Divider(),
              Flexible(
                child: ListView(shrinkWrap: true, children: [
                  if (commissions.isNotEmpty)
                    Text('Commissions',
                        style: TextStyle(
                            color: context.labelColor,
                            fontWeight: FontWeight.w700)),
                  for (final c in commissions)
                    _DueTile(
                      title: '${c['patient_name']} · ${c['commission_rate']}%',
                      amount: c['commission_amount'],
                      status: '${c['status']}',
                      when: '${c['created_at']}',
                    ),
                  if (payouts.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text('Consultations',
                        style: TextStyle(
                            color: context.labelColor,
                            fontWeight: FontWeight.w700)),
                  ],
                  for (final p in payouts)
                    _DueTile(
                      title:
                          '${p['patient_name']} · band ${p['consultation_category']}',
                      amount: p['consultation_fee'],
                      status: '${p['status']}',
                      when: '${p['created_at']}',
                    ),
                ]),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _DueTile extends StatelessWidget {
  final String title;
  final Object? amount;
  final String status;
  final String when;
  const _DueTile(
      {required this.title,
      required this.amount,
      required this.status,
      required this.when});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text(title,
          style: TextStyle(color: context.labelColor, fontSize: 14)),
      subtitle: Text(when.split('T').first,
          style: TextStyle(color: context.hintColor, fontSize: 12)),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(amount),
              style: TextStyle(
                  color: context.labelColor,
                  fontSize: 14,
                  fontWeight: FontWeight.w700)),
          Text(status,
              style: TextStyle(color: statusColor(status), fontSize: 11)),
        ],
      ),
    );
  }
}

class _PrescriberForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _PrescriberForm({this.existing});

  @override
  State<_PrescriberForm> createState() => _PrescriberFormState();
}

class _PrescriberFormState extends State<_PrescriberForm> {
  final _name = TextEditingController();
  final _license = TextEditingController();
  final _specialty = TextEditingController();
  final _phone = TextEditingController();
  final _clinic = TextEditingController();
  final _rate = TextEditingController(text: '0');
  // One controller per consultation band A–E: the doctor's own price list.
  final _fees = {
    for (final b in const ['a', 'b', 'c', 'd', 'e'])
      b: TextEditingController(text: '0')
  };
  int? _hospitalId;
  String? _hospitalName;
  bool _verified = false;
  bool _active = true;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _name.text = '${e['name'] ?? ''}';
      _license.text = '${e['license_number'] ?? ''}';
      _specialty.text = '${e['specialty'] ?? ''}';
      _phone.text = '${e['phone'] ?? ''}';
      _clinic.text = '${e['clinic'] ?? ''}';
      _rate.text = '${e['commission_rate'] ?? 0}';
      _hospitalId = e['hospital'] as int?;
      _hospitalName = e['hospital_name'] as String?;
      _verified = e['is_verified'] == true;
      _active = e['is_active'] == true;
      for (final b in _fees.keys) {
        _fees[b]!.text = '${e['consult_fee_$b'] ?? 0}';
      }
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _license.dispose();
    _specialty.dispose();
    _phone.dispose();
    _clinic.dispose();
    _rate.dispose();
    for (final c in _fees.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickHospital() async {
    final row = await pickRow(
      context,
      path: '/api/prescriptions/hospitals/',
      title: 'Which hospital?',
      hint: 'Name, city or phone…',
      label: (r) => '${r['name']}',
      subtitle: (r) => '${r['city'] ?? ''}',
    );
    if (row != null) {
      setState(() {
        _hospitalId = row['id'] as int?;
        _hospitalName = '${row['name']}';
      });
    }
  }

  Future<void> _newHospital() async {
    final name = TextEditingController();
    final city = TextEditingController();
    final made = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('New hospital'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
              controller: name,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Name')),
          const SizedBox(height: 8),
          TextField(
              controller: city,
              decoration: const InputDecoration(labelText: 'City')),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Add')),
        ],
      ),
    );
    if (made != true || name.text.trim().isEmpty) return;
    try {
      final r = await api.post('/api/prescriptions/hospitals/',
          {'name': name.text.trim(), 'city': city.text.trim()});
      if (!mounted) return;
      setState(() {
        _hospitalId = (r as Map)['id'] as int?;
        _hospitalName = '${r['name']}';
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Name the prescriber.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'license_number': _license.text.trim(),
        'specialty': _specialty.text.trim(),
        'phone': _phone.text.trim(),
        'clinic': _clinic.text.trim(),
        'hospital': _hospitalId,
        'commission_rate': _rate.text.trim(),
        'is_verified': _verified,
        'is_active': _active,
        for (final b in _fees.keys) 'consult_fee_$b': _fees[b]!.text.trim(),
      };
      if (_isEdit) {
        await api.patch(
            '/api/prescriptions/prescribers/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/prescriptions/prescribers/', body);
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
      title: _isEdit ? 'Edit prescriber' : 'New prescriber',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add prescriber',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _license,
              decoration: const InputDecoration(labelText: 'Licence number'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _specialty,
              decoration: const InputDecoration(labelText: 'Specialty'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Phone'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _clinic,
              decoration: const InputDecoration(labelText: 'Clinic'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        InputDecorator(
          decoration: const InputDecoration(labelText: 'Hospital (optional)'),
          child: Row(children: [
            Expanded(
              child: Text(_hospitalName ?? 'Not linked',
                  style: TextStyle(
                      color: _hospitalId == null
                          ? context.hintColor
                          : context.labelColor),
                  overflow: TextOverflow.ellipsis),
            ),
            TextButton(onPressed: _pickHospital, child: const Text('Pick')),
            TextButton(onPressed: _newHospital, child: const Text('New')),
          ]),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _rate,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Commission rate (%)',
            helperText: 'Share of what their scripts sell, 0–100',
          ),
        ),
        const SizedBox(height: 16),
        Text('Consultation bands (₦)',
            style: TextStyle(
                color: context.labelColor, fontWeight: FontWeight.w700)),
        Text('The doctor sets these; the pharmacy charges one and owes it on.',
            style: TextStyle(color: context.hintColor, fontSize: 12)),
        const SizedBox(height: 8),
        for (final b in _fees.keys)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: TextField(
              controller: _fees[b],
              keyboardType: TextInputType.number,
              decoration:
                  InputDecoration(labelText: 'Band ${b.toUpperCase()}'),
            ),
          ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Verified'),
          subtitle: const Text('Licence has been checked'),
          value: _verified,
          onChanged: (v) => setState(() => _verified = v),
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
