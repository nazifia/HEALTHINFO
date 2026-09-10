import 'package:flutter/material.dart';

import '../main.dart';
import '../api.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/snack.dart';

// Cadres that sign in with a practising licence instead of a phone number
// (mirrors LICENSED_ROLES on the backend).
const _licensedRoles = {'doctor', 'nurse', 'midwife', 'chew'};

// What each grant is called on screen, and what it opens. The names are the
// API's (accounts.permissions.MODULE_PRIVILEGES); these are for people.
const _grantLabels = {
  'manage_users': 'User list',
  'pharmacy_admin': 'Pharmacy admin screens',
};

const _grantHints = {
  'manage_users': 'Add and edit the people in this portal',
  'pharmacy_admin': 'Prices, stock corrections and claim settlement',
};

const _roles = [
  'super_admin',
  'tenant_admin',
  'doctor',
  'pharmacist',
  'nurse',
  'midwife',
  'chew',
  'hmo',
  'government',
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
  // The signed-in seat. Which roles and grants the form offers come off it —
  // an insurer's admin staffs its own desk, a facility's admin its facility.
  Map<String, dynamic>? _me;

  @override
  void initState() {
    super.initState();
    _future = api.getList('/api/users/');
    api.me().then((m) {
      if (mounted) setState(() => _me = m);
    });
  }

  void _reload() => setState(() { _future = api.getList('/api/users/'); });

  Future<void> _edit(Map<String, dynamic> u) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _UserForm(user: u, me: _me),
    );
    if (saved == true) _reload();
  }

  Future<void> _create() async {
    // Only the platform admin picks the organization. Every other admin mints
    // into their own module, which the API pins from them
    // (accounts.serializers.apply_admin_scope), so there is nothing to ask.
    List<Map<String, dynamic>> tenants = const [];
    if (Api.moduleOf(_me) == null) {
      try {
        tenants =
            (await api.getList('/api/tenants/')).cast<Map<String, dynamic>>();
      } catch (e) {
        if (mounted) showError(context, '$e');
        return;
      }
    }
    if (!mounted) return;
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _UserForm(tenants: tenants, me: _me),
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
  /// The seat filling the form in. What it may hand out — which roles, which
  /// grants — is read off it, so the form never offers what the API refuses.
  final Map<String, dynamic>? me;
  const _UserForm({this.user, this.tenants, this.me});

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
  late final TextEditingController _license =
      TextEditingController(text: '${widget.user?['license_number'] ?? ''}');
  late String _role = '${widget.user?['role'] ?? 'public'}';
  late bool _active = widget.user?['is_active'] != false;
  int? _tenantId;
  // The scheme an insurer seat answers for. Required by the API for that role,
  // and the list is tenant-scoped: it only answers inside an organization.
  late int? _hmoId = widget.user?['hmo'] as int?;
  List<Map<String, dynamic>> _hmos = const [];
  // The patch a health authority seat reads. Required by the API for that
  // role: the platform rollups narrow to it, so a seat without one reads
  // nothing.
  late int? _jurisdictionId = widget.user?['jurisdiction'] as int?;
  List<Map<String, dynamic>> _jurisdictions = const [];
  // Runs its own portal's user list. Only means anything on the seats that sit
  // outside a facility — an insurer's desk, a health authority's office.
  late bool _isAdmin = widget.user?['is_admin'] == true;
  // Grants on top of the role, offered from what the writer holds themselves.
  late final Set<String> _privileges = {
    ...?(widget.user?['privileges'] as List?)?.map((p) => '$p'),
  };
  bool _busy = false;

  bool get _isEdit => widget.user != null;

  /// Which module the writer works in, and so which fields this form needs.
  /// Null is the platform admin: no module, every role, every field.
  String? get _module => Api.moduleOf(widget.me);

  /// Roles on offer — theirs to assign, and never wider than the API allows.
  List<String> get _roleChoices => Api.manageableRoles(widget.me) ?? _roles;

  /// Grants on offer: what the writer holds, so nobody passes on more than
  /// they have (mirrors apply_admin_scope).
  List<String> get _grantChoices {
    final held = Api.grantsOf(widget.me);
    return (Api.modulePrivileges[_module ?? 'facility'] ?? const <String>{})
        .where(held.contains)
        .toList();
  }

  @override
  void initState() {
    super.initState();
    if (_role == 'hmo') _loadHmos();
    if (_role == 'government') _loadJurisdictions();
  }

  Future<void> _loadJurisdictions() async {
    if (_jurisdictions.isNotEmpty) return;
    try {
      final rows = await api.jurisdictions();
      if (mounted) setState(() => _jurisdictions = rows);
    } catch (_) {
      // Same as the scheme list: the API refuses a seat with no jurisdiction,
      // so this fails loudly on save rather than quietly here.
    }
  }

  Future<void> _loadHmos() async {
    if (_hmos.isNotEmpty) return;
    try {
      final rows = await api.getList('/api/pharmacy/hmos/');
      if (mounted) setState(() => _hmos = rows.cast<Map<String, dynamic>>());
    } catch (_) {
      // Outside an organization there is no scheme list to offer. The API
      // still refuses a seat with no scheme, so this fails loudly on save
      // rather than quietly here.
    }
  }

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? true)) return;
    setState(() => _busy = true);
    try {
      if (_isEdit) {
        await api.patch('/api/users/${widget.user!['id']}/', {
          'username': _username.text.trim(),
          'role': _role,
          'is_active': _active,
          'license_number': _license.text.trim(),
          if (_role == 'hmo') 'hmo': _hmoId,
          if (_role == 'government') 'jurisdiction': _jurisdictionId,
          if (_seatsOutsideFacility) 'is_admin': _isAdmin,
          if (_grantChoices.isNotEmpty) 'privileges': _privileges.toList(),
        });
      } else {
        await api.post('/api/users/', {
          'username': _username.text.trim(),
          'phone': _phone.text.trim(),
          'password': _password.text,
          'role': _role,
          'is_active': _active,
          if (_tenantId != null) 'tenant': _tenantId,
          'license_number': _license.text.trim(),
          if (_role == 'hmo') 'hmo': _hmoId,
          if (_role == 'government') 'jurisdiction': _jurisdictionId,
          if (_seatsOutsideFacility) 'is_admin': _isAdmin,
          if (_grantChoices.isNotEmpty) 'privileges': _privileges.toList(),
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

  /// The seats that sit outside a facility carry the admin flag; a facility's
  /// own staff are admins by role or by grant instead.
  bool get _seatsOutsideFacility => _role == 'hmo' || _role == 'government';

  @override
  void dispose() {
    _username.dispose();
    _phone.dispose();
    _password.dispose();
    _license.dispose();
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
                if (_module == null) SearchableDropdown<int>(
                  initialValue: _tenantId,
                  decoration: const InputDecoration(labelText: 'Tenant'),
                  items: [
                    const DropdownMenuItem(value: null, child: Text('— none (platform) —')),
                    for (final t in tenants)
                      DropdownMenuItem(
                          value: t['id'] as int,
                          child: Text('${t['name']} · ${t['kind'] ?? ''}')),
                  ],
                  onChanged: (v) => setState(() => _tenantId = v),
                ),
              ],
              SearchableDropdown<String>(
                initialValue: _roleChoices.contains(_role)
                    ? _role
                    : _roleChoices.first,
                decoration: const InputDecoration(labelText: 'Role'),
                items: [
                  for (final r in _roleChoices)
                    DropdownMenuItem(value: r, child: Text(r)),
                ],
                onChanged: (v) {
                  setState(() => _role = v ?? _role);
                  if (_role == 'hmo') _loadHmos();
                  if (_role == 'government') _loadJurisdictions();
                },
              ),
              if (_role == 'hmo' && _module != 'scheme')
                SearchableDropdown<int>(
                  initialValue: _hmos.any((h) => h['id'] == _hmoId) ? _hmoId : null,
                  decoration: const InputDecoration(
                    labelText: 'Scheme',
                    helperText: 'Open the organization first — the list is theirs',
                  ),
                  items: [
                    for (final h in _hmos)
                      DropdownMenuItem(
                          value: h['id'] as int, child: Text('${h['name']}')),
                  ],
                  onChanged: (v) => setState(() => _hmoId = v),
                ),
              if (_role == 'government')
                SearchableDropdown<int>(
                  initialValue: _jurisdictions.any((j) => j['id'] == _jurisdictionId)
                      ? _jurisdictionId
                      : null,
                  decoration: const InputDecoration(
                    labelText: 'Jurisdiction',
                    helperText: 'This seat reads it and everything under it',
                  ),
                  items: [
                    for (final j in _jurisdictions)
                      DropdownMenuItem(
                          value: j['id'] as int,
                          child: Text("${j['name']} · ${j['level']}")),
                  ],
                  onChanged: (v) => setState(() => _jurisdictionId = v),
                ),
              if (_licensedRoles.contains(_role))
                TextFormField(
                  controller: _license,
                  decoration: const InputDecoration(
                    labelText: 'License number',
                    helperText: 'This cadre signs in with it instead of a phone',
                  ),
                  textCapitalization: TextCapitalization.characters,
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? 'Required for this role'
                      : null,
                ),
              if (_seatsOutsideFacility)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Portal admin'),
                  subtitle: const Text('Runs this portal’s own user list'),
                  value: _isAdmin,
                  onChanged: (v) => setState(() => _isAdmin = v),
                ),
              if (_grantChoices.isNotEmpty) ...[
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Extra screens',
                      style: TextStyle(
                          color: context.hintColor,
                          fontSize: 12,
                          fontWeight: FontWeight.w700)),
                ),
                for (final grant in _grantChoices)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text(_grantLabels[grant] ?? grant),
                    subtitle: Text(_grantHints[grant] ?? '',
                        style: TextStyle(color: context.hintColor, fontSize: 11)),
                    value: _privileges.contains(grant),
                    onChanged: (on) => setState(() {
                      if (on == true) {
                        _privileges.add(grant);
                      } else {
                        _privileges.remove(grant);
                      }
                    }),
                  ),
              ],
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
