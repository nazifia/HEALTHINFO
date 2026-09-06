import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../api.dart';
import '../config.dart';
import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/snack.dart';

/// Trimmed string, or null when null/blank — so empty fields render as "—".
String? _str(Object? v) {
  final s = v?.toString().trim() ?? '';
  return s.isEmpty ? null : s;
}

/// How the idle window reads on the profile. 0 is off, not "0 minutes".
String _idleLabel(Object? minutes) {
  final m = (minutes as num?)?.toInt();
  if (m == null) return '—';
  if (m == 0) return 'Never';
  return 'After $m minute${m == 1 ? '' : 's'} of inactivity';
}

/// Current account — GET /api/users/me/.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final r = await api.get('/api/users/me/');
    return (r as Map).cast<String, dynamic>();
  }

  Future<void> _editProfile(Map<String, dynamic> u) async {
    final username = TextEditingController(text: u['username']?.toString() ?? '');
    final phone = TextEditingController(text: u['phone']?.toString() ?? '');
    final email = TextEditingController(text: u['email']?.toString() ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit profile'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: username,
              decoration: const InputDecoration(labelText: 'Display name'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Phone'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Save')),
        ],
      ),
    );
    if (saved != true || !mounted) return;
    try {
      await api.patch('/api/users/${u['id']}/', {
        'username': username.text.trim(),
        'phone': phone.text.trim(),
        'email': email.text.trim(),
      });
      if (!mounted) return;
      showSuccess(context, 'Profile updated');
      setState(() { _future = _load(); });
    } on ApiException catch (e) {
      if (mounted) showError(context, e.friendly);
    }
  }

  /// The organization's idle sign-out, for whoever administers it. Reads the
  /// current value rather than the user's own copy: a super-admin working
  /// inside an organization is editing that organization's, not theirs.
  Future<void> _editIdleLogout() async {
    int current;
    try {
      final r = await api.get('/api/tenants/settings/');
      current = ((r as Map)['idle_logout_minutes'] as num?)?.toInt() ?? 30;
    } on ApiException catch (e) {
      if (mounted) showError(context, e.friendly);
      return;
    }
    if (!mounted) return;
    final minutes = TextEditingController(text: '$current');
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Auto sign-out'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Everyone in this organization is signed out after '
                'this many minutes of inactivity. 0 never signs out.'),
            const SizedBox(height: 12),
            TextField(
              controller: minutes,
              keyboardType: TextInputType.number,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Minutes'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Save')),
        ],
      ),
    );
    if (saved != true || !mounted) return;
    final mins = int.tryParse(minutes.text.trim());
    if (mins == null || mins < 0 || mins > 1440) {
      showError(context, 'Enter 0 to 1440 minutes.');
      return;
    }
    try {
      await api.patch('/api/tenants/settings/', {'idle_logout_minutes': mins});
      idleMinutes.value = mins; // applies to this device without a restart
      api.forgetMe();
      if (!mounted) return;
      showSuccess(context, 'Auto sign-out saved');
      setState(() { _future = _load(); });
    } on ApiException catch (e) {
      if (mounted) showError(context, e.friendly);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Center(
              child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
        }
        if (snap.hasError) {
          return EmptyState(
            icon: Icons.error_outline,
            title: 'Could not load profile',
            message: '${snap.error}',
            color: EnhancedTheme.errorRed,
          );
        }
        final u = snap.data!;
        // Phone is the identity; username/email are optional. Fall back to phone
        // so accounts with neither still show a real name + avatar, not "—".
        final username = _str(u['username']) ?? _str(u['phone']) ?? '—';
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          children: [
            Center(
              child: Container(
                height: 88,
                width: 88,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [EnhancedTheme.primaryTeal, EnhancedTheme.accentCyan],
                  ),
                  borderRadius: BorderRadius.circular(26),
                ),
                child: Center(
                  child: Text(
                    username.isEmpty ? '?' : username[0].toUpperCase(),
                    style: GoogleFonts.outfit(
                      color: Colors.white,
                      fontSize: 36,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Text(username,
                  style: GoogleFonts.outfit(
                    color: context.labelColor,
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                  )),
            ),
            const SizedBox(height: 20),
            GlassCard(
              padding: const EdgeInsets.all(8),
              child: Column(
                children: [
                  _Row(icon: Icons.phone_outlined, label: 'Phone', value: _str(u['phone']) ?? '—'),
                  _Row(icon: Icons.mail_outline, label: 'Email', value: _str(u['email']) ?? '—'),
                  _Row(icon: Icons.badge_outlined, label: 'Role', value: _str(u['role']) ?? '—'),
                  _Row(icon: Icons.apartment_outlined, label: 'Tenant', value: _str(u['tenant_name']) ?? _str(u['tenant']) ?? '—'),
                ],
              ),
            ),
            const SizedBox(height: 16),
            if (const {'tenant_admin', 'super_admin'}
                .contains(_str(u['role'])) &&
                tenantSlug.isNotEmpty) ...[
              GlassCard(
                padding: const EdgeInsets.all(8),
                child: ListTile(
                  leading: const Icon(Icons.timer_outlined,
                      color: EnhancedTheme.primaryTeal),
                  title: Text('Auto sign-out',
                      style: TextStyle(color: context.hintColor, fontSize: 12)),
                  subtitle: Text(
                      _idleLabel(u['idle_logout_minutes']),
                      style: TextStyle(
                          color: context.labelColor,
                          fontSize: 15,
                          fontWeight: FontWeight.w600)),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: _editIdleLogout,
                ),
              ),
              const SizedBox(height: 16),
            ],
            FilledButton.icon(
              onPressed: () => _editProfile(u),
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Edit profile'),
            ),
          ],
        );
      },
    );
  }
}

class _Row extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  const _Row({required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon, color: EnhancedTheme.primaryTeal),
      title: Text(label, style: TextStyle(color: context.hintColor, fontSize: 12)),
      subtitle: Text(value,
          style: TextStyle(
              color: context.labelColor,
              fontSize: 15,
              fontWeight: FontWeight.w600)),
    );
  }
}
