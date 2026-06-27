import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/snack.dart';

const _roles = [
  'super_admin',
  'tenant_admin',
  'doctor',
  'pharmacist',
  'nurse',
  'public',
];

/// Super-admin user administration — edits over /api/users/ (cross-tenant).
/// Change a user's role or activate/deactivate them. Tenant is set at signup
/// and shown read-only here.
class UserManagementScreen extends StatefulWidget {
  const UserManagementScreen({super.key});

  @override
  State<UserManagementScreen> createState() => _UserManagementScreenState();
}

class _UserManagementScreenState extends State<UserManagementScreen> {
  late Future<List<dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = api.getList('/api/users/');
  }

  void _reload() => setState(() => _future = api.getList('/api/users/'));

  Future<void> _edit(Map<String, dynamic> u) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _UserForm(user: u),
    );
    if (saved == true) _reload();
  }

  Future<void> _create() async {
    List<Map<String, dynamic>> tenants;
    try {
      tenants = (await api.getList('/api/tenants/')).cast<Map<String, dynamic>>();
    } catch (e) {
      if (mounted) showError(context, '$e');
      return;
    }
    if (!mounted) return;
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _UserForm(tenants: tenants),
    );
    if (saved == true) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'fab_user',
        onPressed: _create,
        backgroundColor: EnhancedTheme.accentPurple,
        icon: const Icon(Icons.person_add_alt),
        label: const Text('New user'),
      ),
      body: _list(),
    );
  }

  Widget _list() {
    return RefreshIndicator(
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
                title: 'Could not load users',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final rows = snap.data!.cast<Map<String, dynamic>>();
          if (rows.isEmpty) {
            return ListView(children: const [
              SizedBox(height: 80),
              EmptyState(
                icon: Icons.group_outlined,
                title: 'No users',
              ),
            ]);
          }
          return ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
            itemCount: rows.length,
            itemBuilder: (_, i) => _UserCard(u: rows[i], onTap: () => _edit(rows[i])),
          );
        },
      ),
    );
  }
}

class _UserCard extends StatelessWidget {
  final Map<String, dynamic> u;
  final VoidCallback onTap;
  const _UserCard({required this.u, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final active = u['is_active'] != false;
    final name = '${u['username'] ?? ''}'.trim();
    final title = name.isEmpty ? '${u['phone'] ?? '—'}' : name;
    return GlassCard(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      onTap: onTap,
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: EnhancedTheme.accentPurple.withValues(alpha: 0.15),
            child: Icon(
              active ? Icons.person : Icons.person_off,
              color: active ? EnhancedTheme.accentPurple : context.hintColor,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: TextStyle(
                        color: context.labelColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 15)),
                Text(
                  '${u['phone'] ?? ''} · ${u['tenant_name'] ?? '—'}',
                  style: TextStyle(color: context.hintColor, fontSize: 12),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: EnhancedTheme.primaryTeal.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text('${u['role'] ?? 'public'}',
                style: const TextStyle(
                    color: EnhancedTheme.primaryTeal,
                    fontSize: 11,
                    fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}

/// Edit an existing user (pass `user`) or mint a new one (pass `tenants` for the
/// tenant picker). Pops `true` on save.
class _UserForm extends StatefulWidget {
  final Map<String, dynamic>? user;
  final List<Map<String, dynamic>>? tenants;
  const _UserForm({this.user, this.tenants});

  @override
  State<_UserForm> createState() => _UserFormState();
}

class _UserFormState extends State<_UserForm> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _username =
      TextEditingController(text: '${widget.user?['username'] ?? ''}');
  late final TextEditingController _phone =
      TextEditingController(text: '${widget.user?['phone'] ?? ''}');
  final TextEditingController _password = TextEditingController();
  late String _role = '${widget.user?['role'] ?? 'public'}';
  late bool _active = widget.user?['is_active'] != false;
  int? _tenantId;
  bool _busy = false;

  bool get _isEdit => widget.user != null;

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? true)) return;
    setState(() => _busy = true);
    try {
      if (_isEdit) {
        await api.patch('/api/users/${widget.user!['id']}/', {
          'username': _username.text.trim(),
          'role': _role,
          'is_active': _active,
        });
      } else {
        await api.post('/api/users/', {
          'username': _username.text.trim(),
          'phone': _phone.text.trim(),
          'password': _password.text,
          'role': _role,
          'is_active': _active,
          if (_tenantId != null) 'tenant': _tenantId,
        });
      }
      if (!mounted) return;
      showSuccess(context, _isEdit ? 'User updated.' : 'User created.');
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
    _username.dispose();
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tenants = widget.tenants ?? const [];
    return AlertDialog(
      title: Text(_isEdit ? '${widget.user!['phone'] ?? 'User'}' : 'New user'),
      content: Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _username,
                decoration: const InputDecoration(labelText: 'Display name'),
                textCapitalization: TextCapitalization.words,
              ),
              if (!_isEdit) ...[
                TextFormField(
                  controller: _phone,
                  decoration: const InputDecoration(labelText: 'Phone'),
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Required' : null,
                ),
                TextFormField(
                  controller: _password,
                  decoration: const InputDecoration(labelText: 'Password'),
                  obscureText: true,
                  validator: (v) =>
                      (v == null || v.length < 8) ? 'Min 8 characters' : null,
                ),
                DropdownButtonFormField<int>(
                  initialValue: _tenantId,
                  decoration: const InputDecoration(labelText: 'Tenant'),
                  items: [
                    const DropdownMenuItem(value: null, child: Text('— none (platform) —')),
                    for (final t in tenants)
                      DropdownMenuItem(
                          value: t['id'] as int, child: Text('${t['name']}')),
                  ],
                  onChanged: (v) => setState(() => _tenantId = v),
                ),
              ],
              DropdownButtonFormField<String>(
                initialValue: _roles.contains(_role) ? _role : 'public',
                decoration: const InputDecoration(labelText: 'Role'),
                items: [
                  for (final r in _roles)
                    DropdownMenuItem(value: r, child: Text(r)),
                ],
                onChanged: (v) => setState(() => _role = v ?? _role),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Active'),
                value: _active,
                onChanged: (v) => setState(() => _active = v),
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
