import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Branches — GET /api/branches/.
///
/// A tenant is the business; a branch is a shop. Stock, sales, shifts and
/// scripts carry the branch they happened at, so a two-shop pharmacy can count
/// one drawer without counting the other's. Staff read the list; only the
/// pharmacy admin opens, renames or retires a site.
class BranchesScreen extends StatelessWidget {
  const BranchesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return ReportListScreen(
          path: '/api/branches/',
          searchHint: 'Search branches…',
          fabLabel: 'Add branch',
          showFab: admin,
          emptyIcon: Icons.storefront_outlined,
          emptyTitle: 'No branches yet',
          emptyMessage: admin
              ? 'Tap "Add branch" and mark the head office as the main one.'
              : 'The pharmacy admin keeps the branch list.',
          savedMessage: 'Branch saved.',
          filters: const [
            ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
              'true': 'Open',
              'false': 'Closed',
            }),
          ],
          card: (row, reload, edit) =>
              _BranchCard(row: row, admin: admin, edit: edit),
          form: (existing) => _BranchForm(existing: existing),
        );
      },
    );
  }
}

class _BranchCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _BranchCard(
      {required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    final contact = [
      '${row['phone'] ?? ''}',
      '${row['email'] ?? ''}',
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
          if (row['is_main'] == true)
            const ReportBadge(text: 'main', color: EnhancedTheme.primaryTeal),
          if (row['is_active'] != true) ...[
            const SizedBox(width: 6),
            const ReportBadge(text: 'closed', color: EnhancedTheme.errorRed),
          ],
          if (admin)
            IconButton(
                icon: const Icon(Icons.edit_outlined, size: 18),
                onPressed: edit),
        ]),
        if ('${row['address'] ?? ''}'.trim().isNotEmpty) ...[
          const SizedBox(height: 6),
          Text('${row['address']}',
              style: TextStyle(color: context.hintColor, fontSize: 13)),
        ],
        if (contact.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(contact,
              style: TextStyle(color: context.hintColor, fontSize: 13)),
        ],
      ]),
    );
  }
}

class _BranchForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _BranchForm({this.existing});

  @override
  State<_BranchForm> createState() => _BranchFormState();
}

class _BranchFormState extends State<_BranchForm> {
  final _name = TextEditingController();
  final _address = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  bool _active = true;
  bool _main = false;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _name.text = '${e['name'] ?? ''}';
      _address.text = '${e['address'] ?? ''}';
      _phone.text = '${e['phone'] ?? ''}';
      _email.text = '${e['email'] ?? ''}';
      _active = e['is_active'] == true;
      _main = e['is_main'] == true;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _address.dispose();
    _phone.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Name the branch.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'address': _address.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim(),
        'is_active': _active,
        'is_main': _main,
      };
      if (_isEdit) {
        await api.patch('/api/branches/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/branches/', body);
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
      title: _isEdit ? 'Edit branch' : 'New branch',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add branch',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Branch name'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _address,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Address'),
        ),
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
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
          ),
        ]),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Open'),
          subtitle: const Text('Closed branches are hidden; their data stays'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Head office'),
          // The API demotes whichever branch held it, so this never fails as a
          // clash — it just moves.
          subtitle: const Text('One per pharmacy; setting it moves the flag'),
          value: _main,
          onChanged: (v) => setState(() => _main = v),
        ),
      ],
    );
  }
}
