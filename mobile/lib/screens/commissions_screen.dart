import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Staff commission terms — GET /api/reports/commission-configs/.
///
/// What each member of staff earns on what they sell: a percentage, plus an
/// optional flat bonus. Staff read the list — knowing your own rate is
/// reasonable — but only the admin sets one, because it is the pharmacy's
/// money going out.
///
/// Switching a row off stops it earning without losing what the rate was, so
/// last month's payout still reconciles.
class CommissionsScreen extends StatelessWidget {
  const CommissionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return ReportListScreen(
          path: '/api/reports/commission-configs/',
          fabLabel: 'Set a rate',
          showFab: admin,
          emptyIcon: Icons.percent_outlined,
          emptyTitle: 'No commission set',
          emptyMessage: admin
              ? 'Staff with no rate earn nothing on what they sell.'
              : 'The pharmacy admin sets commission rates.',
          savedMessage: 'Commission terms saved.',
          filters: const [
            ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
              'true': 'Earning',
              'false': 'Switched off',
            }),
          ],
          card: (row, reload, edit) =>
              _ConfigCard(row: row, admin: admin, edit: edit),
          form: (existing) => _ConfigForm(existing: existing),
        );
      },
    );
  }
}

class _ConfigCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _ConfigCard(
      {required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    final bonus = num.tryParse('${row['fixed_bonus']}') ?? 0;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${row['user_name'] ?? 'Staff'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
            Text(
                '${row['rate']}% of sales'
                '${bonus > 0 ? ' + ${money(bonus)} bonus' : ''}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
          ]),
        ),
        if (row['is_active'] != true)
          const ReportBadge(text: 'off', color: EnhancedTheme.errorRed),
        if (admin)
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
      ]),
    );
  }
}

class _ConfigForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _ConfigForm({this.existing});

  @override
  State<_ConfigForm> createState() => _ConfigFormState();
}

class _ConfigFormState extends State<_ConfigForm> {
  final _rate = TextEditingController(text: '0');
  final _bonus = TextEditingController();
  int? _userId;
  String? _userName;
  bool _active = true;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _rate.text = '${e['rate'] ?? 0}';
      _bonus.text = e['fixed_bonus'] == null ? '' : '${e['fixed_bonus']}';
      _userId = e['user'] as int?;
      _userName = e['user_name'] as String?;
      _active = e['is_active'] == true;
    }
  }

  @override
  void dispose() {
    _rate.dispose();
    _bonus.dispose();
    super.dispose();
  }

  Future<void> _pickUser() async {
    final row = await pickRow(
      context,
      path: '/api/users/',
      title: 'Whose rate?',
      hint: 'Username or phone…',
      label: (r) => '${r['username']}',
      subtitle: (r) => '${r['role'] ?? ''}',
    );
    if (row != null) {
      setState(() {
        _userId = row['id'] as int?;
        _userName = '${row['username']}';
      });
    }
  }

  Future<void> _submit() async {
    if (_userId == null) {
      setState(() => _error = 'Pick whose rate this is.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'user': _userId,
        'rate': _rate.text.trim(),
        // Null, not zero: no bonus at all reads differently from a bonus of
        // nothing, and the API's field is nullable for exactly that.
        'fixed_bonus':
            _bonus.text.trim().isEmpty ? null : _bonus.text.trim(),
        'is_active': _active,
      };
      if (_isEdit) {
        await api.patch(
            '/api/reports/commission-configs/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/reports/commission-configs/', body);
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
      title: _isEdit ? 'Edit commission' : 'Set a commission rate',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Set rate',
      onSubmit: _submit,
      children: [
        InputDecorator(
          decoration: const InputDecoration(labelText: 'Staff member'),
          child: Row(children: [
            Expanded(
              child: Text(_userName ?? 'Not picked',
                  style: TextStyle(
                      color: _userId == null
                          ? context.hintColor
                          : context.labelColor),
                  overflow: TextOverflow.ellipsis),
            ),
            TextButton(
                onPressed: _pickUser,
                child: Text(_userId == null ? 'Pick' : 'Change')),
          ]),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _rate,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Rate (%)',
            helperText: 'Share of what they sell, 0–100',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _bonus,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Fixed bonus (₦, optional)',
            helperText: 'Added once per period on top of the rate',
          ),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Earning'),
          subtitle: const Text('Switching off keeps the rate on record'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
      ],
    );
  }
}
