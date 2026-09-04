import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Cashiers — GET /api/pos/cashiers/.
///
/// Who may take money, and at which counter. A payment request can only be
/// accepted by someone on this list, so it is the admin's to keep: adding a
/// row here is handing somebody the till.
class CashiersScreen extends StatelessWidget {
  const CashiersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return ReportListScreen(
          path: '/api/pos/cashiers/',
          searchHint: 'Name or code…',
          fabLabel: 'Add cashier',
          showFab: admin,
          emptyIcon: Icons.badge_outlined,
          emptyTitle: 'No cashiers set up',
          emptyMessage: admin
              ? 'Add the staff who take money at the till.'
              : 'The pharmacy admin decides who takes money.',
          savedMessage: 'Cashier saved.',
          filters: const [
            ReportFilter(param: 'kind', anyLabel: 'Any counter', options: {
              'retail': 'Retail',
              'wholesale': 'Wholesale',
              'both': 'Both',
            }),
            ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
              'true': 'Active',
              'false': 'Stood down',
            }),
          ],
          card: (row, reload, edit) =>
              _CashierCard(row: row, admin: admin, edit: edit),
          form: (existing) => _CashierForm(existing: existing),
        );
      },
    );
  }
}

class _CashierCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _CashierCard(
      {required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${row['name']?.toString().isNotEmpty == true ? row['name'] : row['user_name'] ?? 'Cashier'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
            Text('${row['code'] ?? ''} · ${row['kind']} counter',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
          ]),
        ),
        if (row['is_active'] != true)
          const ReportBadge(text: 'stood down', color: EnhancedTheme.errorRed),
        if (admin)
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
      ]),
    );
  }
}

class _CashierForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _CashierForm({this.existing});

  @override
  State<_CashierForm> createState() => _CashierFormState();
}

class _CashierFormState extends State<_CashierForm> {
  final _name = TextEditingController();
  int? _userId;
  String? _userName;
  String _kind = 'retail';
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
      _userId = e['user'] as int?;
      _userName = e['user_name'] as String?;
      _kind = '${e['kind'] ?? 'retail'}';
      _active = e['is_active'] == true;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _pickUser() async {
    final row = await pickRow(
      context,
      path: '/api/users/',
      title: 'Which member of staff?',
      hint: 'Username or phone…',
      label: (r) => '${r['username']}',
      subtitle: (r) => '${r['role'] ?? ''} · ${r['phone'] ?? ''}',
    );
    if (row != null) {
      setState(() {
        _userId = row['id'] as int?;
        _userName = '${row['username']}';
        if (_name.text.trim().isEmpty) _name.text = '${row['username']}';
      });
    }
  }

  Future<void> _submit() async {
    if (_userId == null) {
      setState(() => _error = 'Pick the member of staff this is.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'user': _userId,
        'name': _name.text.trim(),
        'kind': _kind,
        'is_active': _active,
      };
      if (_isEdit) {
        await api.patch('/api/pos/cashiers/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pos/cashiers/', body);
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
      title: _isEdit ? 'Edit cashier' : 'New cashier',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add cashier',
      onSubmit: _submit,
      children: [
        InputDecorator(
          decoration: const InputDecoration(labelText: 'Staff account'),
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
          controller: _name,
          decoration: const InputDecoration(
            labelText: 'Display name',
            helperText: 'What shows on a receipt; the code is generated',
          ),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _kind,
          decoration: const InputDecoration(labelText: 'Serves'),
          items: const [
            DropdownMenuItem(value: 'retail', child: Text('Retail counter')),
            DropdownMenuItem(
                value: 'wholesale', child: Text('Wholesale counter')),
            DropdownMenuItem(value: 'both', child: Text('Both')),
          ],
          onChanged: (v) => setState(() => _kind = v ?? 'retail'),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Active'),
          subtitle: const Text('Stood-down cashiers cannot take a basket'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
      ],
    );
  }
}
