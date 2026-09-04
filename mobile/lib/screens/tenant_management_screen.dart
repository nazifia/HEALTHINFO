import 'package:flutter/material.dart';

import '../main.dart';
import '../config.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/snack.dart';

/// Super-admin tenant administration — CRUD over /api/tenants/.
/// Hospitals and pharmacies are listed separately (the kind-scoped list
/// endpoints); create/edit and approve/reject/suspend still hit /api/tenants/.
///
/// Also the tenant switcher: a super-admin belongs to no organization, so
/// until they open one every tenant-scoped screen answers empty. Opening one
/// POSTs /open/ first, which writes the audit row naming who went where.
class TenantManagementScreen extends StatefulWidget {
  const TenantManagementScreen({super.key});

  @override
  State<TenantManagementScreen> createState() => _TenantManagementScreenState();
}

class _TenantManagementScreenState extends State<TenantManagementScreen> {
  late Future<List<dynamic>> _future;
  String _kind = 'hospitals'; // 'hospitals' | 'pharmacies'

  @override
  void initState() {
    super.initState();
    _future = api.getList('/api/tenants/$_kind/');
  }

  void _reload() => setState(() => _future = api.getList('/api/tenants/$_kind/'));

  Future<void> _post(String path, String ok) async {
    try {
      await api.post(path);
      if (!mounted) return;
      showSuccess(context, ok);
      _reload();
    } catch (e) {
      if (mounted) showError(context, '$e');
    }
  }

  Future<void> _openAs(Map<String, dynamic> t) async {
    try {
      await api.post('/api/tenants/${t['id']}/open/');
      await setTenant('${t['slug']}');
      if (!mounted) return;
      showSuccess(context, 'Working in ${t['name']}.');
      setState(() {});
    } catch (e) {
      if (mounted) showError(context, '$e');
    }
  }

  Future<void> _leave() async {
    await setTenant('');
    if (!mounted) return;
    showSuccess(context, 'Left the organization.');
    setState(() {});
  }

  Future<void> _showAccessLog(Map<String, dynamic> t) async {
    List<dynamic> rows;
    try {
      rows = await api.getList('/api/tenants/${t['id']}/access-log/');
    } catch (e) {
      if (mounted) showError(context, '$e');
      return;
    }
    if (!mounted) return;
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Who opened ${t['name']}'),
        content: SizedBox(
          width: 360,
          child: rows.isEmpty
              ? const Text('Nobody has opened this organization yet.')
              : ListView(
                  shrinkWrap: true,
                  children: [
                    for (final r in rows.cast<Map<String, dynamic>>())
                      ListTile(
                        dense: true,
                        leading: const Icon(Icons.person_outline, size: 18),
                        title: Text('${r['user_phone'] ?? r['user'] ?? '—'}'),
                        subtitle: Text('${r['created_at'] ?? ''}'),
                      ),
                  ],
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  Future<void> _openForm({Map<String, dynamic>? tenant}) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _TenantForm(
        tenant: tenant,
        defaultKind: _kind == 'hospitals' ? 'hospital' : 'pharmacy',
      ),
    );
    if (saved == true) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'fab_tenant',
        onPressed: () => _openForm(),
        backgroundColor: EnhancedTheme.accentPurple,
        icon: const Icon(Icons.add),
        label: Text(_kind == 'hospitals' ? 'New hospital' : 'New pharmacy'),
      ),
      body: Column(children: [
        if (tenantSlug.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: GlassCard(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(children: [
                const Icon(Icons.business_outlined, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Working in $tenantSlug',
                      style: TextStyle(color: context.labelColor)),
                ),
                TextButton(onPressed: _leave, child: const Text('Leave')),
              ]),
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'hospitals', label: Text('Hospitals')),
              ButtonSegment(value: 'pharmacies', label: Text('Pharmacies')),
            ],
            selected: {_kind},
            onSelectionChanged: (s) {
              _kind = s.first;
              _reload();
            },
          ),
        ),
        Expanded(child: RefreshIndicator(
        onRefresh: () async {
          _reload();
          await _future;
        },
        child: FutureBuilder<List<dynamic>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const SkeletonCards(cards: 6);
            }
            if (snap.hasError) {
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: Icons.error_outline,
                  title: 'Could not load $_kind',
                  message: '${snap.error}',
                  color: EnhancedTheme.errorRed,
                ),
              ]);
            }
            final rows = snap.data!.cast<Map<String, dynamic>>();
            if (rows.isEmpty) {
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: Icons.apartment_outlined,
                  title: 'No $_kind yet',
                  message: 'Create the first organization.',
                ),
              ]);
            }
            return ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
              itemCount: rows.length,
              itemBuilder: (_, i) => _TenantCard(
                t: rows[i],
                onOpenAs: () => _openAs(rows[i]),
                onAccessLog: () => _showAccessLog(rows[i]),
                onEdit: () => _openForm(tenant: rows[i]),
                onApprove: () =>
                    _post('/api/tenants/${rows[i]['id']}/approve/', 'Approved.'),
                onReject: () =>
                    _post('/api/tenants/${rows[i]['id']}/reject/', 'Rejected.'),
                onSuspend: () => _post(
                    '/api/tenants/${rows[i]['id']}/suspend/', 'Status changed.'),
              ),
            );
          },
        ),
      )),
      ]),
    );
  }
}

class _TenantCard extends StatelessWidget {
  final Map<String, dynamic> t;
  final VoidCallback onOpenAs, onAccessLog, onEdit, onApprove, onReject, onSuspend;
  const _TenantCard({
    required this.t,
    required this.onOpenAs,
    required this.onAccessLog,
    required this.onEdit,
    required this.onApprove,
    required this.onReject,
    required this.onSuspend,
  });

  Color _subColor(String s) => switch (s) {
        'approved' => EnhancedTheme.successGreen,
        'rejected' => EnhancedTheme.errorRed,
        _ => EnhancedTheme.accentOrange,
      };

  @override
  Widget build(BuildContext context) {
    final sub = '${t['subscription_status'] ?? 'pending'}';
    final status = '${t['status'] ?? 'active'}';
    final suspended = status == 'suspended';
    return GlassCard(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      onTap: onEdit,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${t['name'] ?? '—'}',
                        style: TextStyle(
                            color: context.labelColor,
                            fontWeight: FontWeight.w800,
                            fontSize: 16)),
                    Text('${t['slug'] ?? ''} · ${t['user_count'] ?? 0} users',
                        style:
                            TextStyle(color: context.hintColor, fontSize: 12)),
                  ],
                ),
              ),
              _Chip(label: sub, color: _subColor(sub)),
              if (suspended) ...[
                const SizedBox(width: 6),
                const _Chip(label: 'suspended', color: EnhancedTheme.errorRed),
              ],
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            children: [
              _Act(icon: Icons.login, label: 'Open as', onTap: onOpenAs,
                  color: EnhancedTheme.accentPurple),
              _Act(icon: Icons.history, label: 'Who opened', onTap: onAccessLog,
                  color: EnhancedTheme.primaryTeal),
              if (sub != 'approved')
                _Act(icon: Icons.check, label: 'Approve', onTap: onApprove,
                    color: EnhancedTheme.successGreen),
              if (sub != 'rejected')
                _Act(icon: Icons.close, label: 'Reject', onTap: onReject,
                    color: EnhancedTheme.errorRed),
              _Act(
                icon: suspended ? Icons.play_arrow : Icons.pause,
                label: suspended ? 'Reactivate' : 'Suspend',
                onTap: onSuspend,
                color: EnhancedTheme.accentOrange,
              ),
              _Act(icon: Icons.edit, label: 'Edit', onTap: onEdit,
                  color: EnhancedTheme.primaryTeal),
            ],
          ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color color;
  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(label.toUpperCase(),
            style: TextStyle(
                color: color, fontSize: 10, fontWeight: FontWeight.w700)),
      );
}

class _Act extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color color;
  const _Act(
      {required this.icon,
      required this.label,
      required this.onTap,
      required this.color});

  @override
  Widget build(BuildContext context) => TextButton.icon(
        onPressed: onTap,
        icon: Icon(icon, size: 16, color: color),
        label: Text(label, style: TextStyle(color: color, fontSize: 13)),
        style: TextButton.styleFrom(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            minimumSize: const Size(0, 36)),
      );
}

/// Create (no id) or edit (id present) a tenant. Pops `true` on save.
class _TenantForm extends StatefulWidget {
  final Map<String, dynamic>? tenant;
  final String defaultKind;
  const _TenantForm({this.tenant, required this.defaultKind});

  @override
  State<_TenantForm> createState() => _TenantFormState();
}

class _TenantFormState extends State<_TenantForm> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _name =
      TextEditingController(text: '${widget.tenant?['name'] ?? ''}');
  late final TextEditingController _slug =
      TextEditingController(text: '${widget.tenant?['slug'] ?? ''}');
  late final TextEditingController _address =
      TextEditingController(text: '${widget.tenant?['address'] ?? ''}');
  late final TextEditingController _contact =
      TextEditingController(text: '${widget.tenant?['contact'] ?? ''}');
  late String _kind = '${widget.tenant?['kind'] ?? widget.defaultKind}';
  bool _busy = false;

  bool get _isEdit => widget.tenant != null;

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    final body = {
      'name': _name.text.trim(),
      'slug': _slug.text.trim(),
      'kind': _kind,
      'address': _address.text.trim(),
      'contact': _contact.text.trim(),
    };
    try {
      if (_isEdit) {
        await api.patch('/api/tenants/${widget.tenant!['id']}/', body);
      } else {
        await api.post('/api/tenants/', body);
      }
      if (!mounted) return;
      showSuccess(context, _isEdit ? 'Tenant updated.' : 'Tenant created.');
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        showError(context, '$e');
      }
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _slug.dispose();
    _address.dispose();
    _contact.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(_isEdit ? 'Edit tenant' : 'New tenant'),
      content: Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
              TextFormField(
                controller: _slug,
                enabled: !_isEdit, // slug is the tenant key; don't rename live
                decoration: const InputDecoration(labelText: 'Slug'),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
              DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: 'hospital', child: Text('Hospital')),
                  DropdownMenuItem(value: 'pharmacy', child: Text('Pharmacy')),
                ],
                onChanged: (v) => setState(() => _kind = v ?? _kind),
              ),
              TextFormField(
                controller: _address,
                decoration: const InputDecoration(labelText: 'Address'),
              ),
              TextFormField(
                controller: _contact,
                decoration: const InputDecoration(labelText: 'Contact'),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _busy ? null : _save,
          child: _busy
              ? const SizedBox(
                  width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Save'),
        ),
      ],
    );
  }
}
