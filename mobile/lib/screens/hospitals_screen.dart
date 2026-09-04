import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import 'report_scaffold.dart';

/// Hospitals — GET /api/prescriptions/hospitals/.
///
/// The clinics prescribers write from. A prescriber can be linked to one when
/// they are added, and this screen is where the record itself is corrected —
/// a clinic that moved, changed its phone, or was typed in wrong at the till.
/// Staff read the list; only the pharmacy admin writes it.
class HospitalsScreen extends StatelessWidget {
  const HospitalsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return ReportListScreen(
          path: '/api/prescriptions/hospitals/',
          searchHint: 'Name, city or phone…',
          fabLabel: 'Add hospital',
          showFab: admin,
          emptyIcon: Icons.local_hospital_outlined,
          emptyTitle: 'No hospitals yet',
          emptyMessage: admin
              ? 'Add the clinics your prescribers write from.'
              : 'The pharmacy admin keeps the hospital list.',
          savedMessage: 'Hospital saved.',
          card: (row, reload, edit) =>
              _HospitalCard(row: row, admin: admin, edit: edit),
          onTap: (row) => _prescribers(context, row),
          form: (existing) => _HospitalForm(existing: existing),
        );
      },
    );
  }

  /// Who writes from here — the prescriber list narrowed to this hospital.
  static Future<void> _prescribers(
      BuildContext context, Map<String, dynamic> row) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _PrescribersSheet(hospital: row),
    );
  }
}

class _HospitalCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _HospitalCard(
      {required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    final where = [
      '${row['city'] ?? ''}',
      '${row['phone'] ?? ''}',
    ].where((v) => v.trim().isNotEmpty).join(' · ');
    final count = row['prescriber_count'] ?? 0;
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
          if (admin)
            IconButton(
                icon: const Icon(Icons.edit_outlined, size: 18),
                onPressed: edit),
        ]),
        if (where.isNotEmpty)
          Text(where, style: TextStyle(color: context.hintColor, fontSize: 13)),
        const SizedBox(height: 4),
        Text('$count ${count == 1 ? 'prescriber' : 'prescribers'}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if ('${row['address'] ?? ''}'.trim().isNotEmpty) ...[
          const SizedBox(height: 4),
          Text('${row['address']}',
              style: TextStyle(color: context.hintColor, fontSize: 13)),
        ],
      ]),
    );
  }
}

class _HospitalForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _HospitalForm({this.existing});

  @override
  State<_HospitalForm> createState() => _HospitalFormState();
}

class _HospitalFormState extends State<_HospitalForm> {
  final _name = TextEditingController();
  final _city = TextEditingController();
  final _phone = TextEditingController();
  final _address = TextEditingController();
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _name.text = '${e['name'] ?? ''}';
      _city.text = '${e['city'] ?? ''}';
      _phone.text = '${e['phone'] ?? ''}';
      _address.text = '${e['address'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _city.dispose();
    _phone.dispose();
    _address.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Name the hospital.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'city': _city.text.trim(),
        'phone': _phone.text.trim(),
        'address': _address.text.trim(),
      };
      if (_isEdit) {
        await api.patch(
            '/api/prescriptions/hospitals/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/prescriptions/hospitals/', body);
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
      title: _isEdit ? 'Edit hospital' : 'New hospital',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add hospital',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          // The API keeps one row per name per pharmacy, so a duplicate comes
          // back as a save error rather than a second clinic.
          decoration: const InputDecoration(labelText: 'Hospital name'),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _city,
              decoration: const InputDecoration(labelText: 'City'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Phone'),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _address,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Address'),
        ),
      ],
    );
  }
}

/// The prescribers linked to one hospital. Read-only — editing a doctor stays
/// on the prescribers screen, which owns their rates and bands.
class _PrescribersSheet extends StatelessWidget {
  final Map<String, dynamic> hospital;
  const _PrescribersSheet({required this.hospital});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints:
          BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.7),
      decoration: BoxDecoration(
        color: context.scaffoldBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: FutureBuilder<List<dynamic>>(
        future: api.getList('/api/prescriptions/prescribers/',
            {'hospital': '${hospital['id']}'}),
        builder: (context, snap) {
          final rows =
              (snap.data ?? const []).cast<Map<String, dynamic>>().toList();
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${hospital['name']}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
              const SizedBox(height: 12),
              if (snap.connectionState == ConnectionState.waiting)
                const LinearProgressIndicator(minHeight: 2)
              else if (rows.isEmpty)
                Text('No prescribers write from here yet.',
                    style: TextStyle(color: context.hintColor, fontSize: 13))
              else
                Flexible(
                  child: ListView(shrinkWrap: true, children: [
                    for (final p in rows)
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        title: Text('${p['name']}',
                            style: TextStyle(
                                color: context.labelColor, fontSize: 14)),
                        subtitle: Text(
                            '${p['specialty'] ?? ''}'.trim().isEmpty
                                ? '${p['commission_rate']}% commission'
                                : "${p['specialty']} · ${p['commission_rate']}% commission",
                            style: TextStyle(
                                color: context.hintColor, fontSize: 12)),
                        trailing: p['is_active'] == true
                            ? null
                            : const ReportBadge(
                                text: 'retired',
                                color: EnhancedTheme.errorRed),
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
