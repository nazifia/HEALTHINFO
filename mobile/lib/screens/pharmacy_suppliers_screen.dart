import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Suppliers — GET /api/pharmacy/suppliers/.
///
/// Batches and orders point at a row here rather than carrying a typed-in name,
/// so "who supplied this recalled batch" has one answer. Staff read the list;
/// only the pharmacy admin keeps it.
class PharmacySuppliersScreen extends StatelessWidget {
  const PharmacySuppliersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return ReportListScreen(
          path: '/api/pharmacy/suppliers/',
          searchHint: 'Search suppliers…',
          fabLabel: 'Add supplier',
          showFab: admin,
          emptyIcon: Icons.local_shipping_outlined,
          emptyTitle: 'No suppliers yet',
          emptyMessage: admin
              ? 'Tap "Add supplier" to start the list.'
              : 'The pharmacy admin keeps the supplier list.',
          savedMessage: 'Supplier saved.',
          filters: const [
            ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
              'true': 'Active',
              'false': 'Retired',
            }),
          ],
          card: (row, reload, edit) =>
              _SupplierCard(row: row, admin: admin, edit: edit),
          form: (existing) => _SupplierForm(existing: existing),
        );
      },
    );
  }
}

class _SupplierCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _SupplierCard(
      {required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    final contact = [
      '${row['contact_person'] ?? ''}',
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
          if (row['is_active'] != true)
            const ReportBadge(text: 'retired', color: EnhancedTheme.errorRed),
          if (admin)
            IconButton(
                icon: const Icon(Icons.edit_outlined, size: 18),
                onPressed: edit),
        ]),
        if (contact.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(contact,
              style: TextStyle(color: context.hintColor, fontSize: 13)),
        ],
      ]),
    );
  }
}

class _SupplierForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _SupplierForm({this.existing});

  @override
  State<_SupplierForm> createState() => _SupplierFormState();
}

class _SupplierFormState extends State<_SupplierForm> {
  final _name = TextEditingController();
  final _contact = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _address = TextEditingController();
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
      _contact.text = '${e['contact_person'] ?? ''}';
      _phone.text = '${e['phone'] ?? ''}';
      _email.text = '${e['email'] ?? ''}';
      _address.text = '${e['address'] ?? ''}';
      _active = e['is_active'] == true;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _contact.dispose();
    _phone.dispose();
    _email.dispose();
    _address.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Name the supplier.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'contact_person': _contact.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim(),
        'address': _address.text.trim(),
        'is_active': _active,
      };
      if (_isEdit) {
        await api.patch(
            '/api/pharmacy/suppliers/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pharmacy/suppliers/', body);
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
      title: _isEdit ? 'Edit supplier' : 'New supplier',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add supplier',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _contact,
          decoration: const InputDecoration(labelText: 'Contact person'),
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
        const SizedBox(height: 12),
        TextField(
          controller: _address,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Address'),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Active'),
          subtitle: const Text('Offered when receiving stock or ordering'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
      ],
    );
  }
}
