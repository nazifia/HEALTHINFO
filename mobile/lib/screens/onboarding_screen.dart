import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../config.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';

/// Self-serve organization signup. POSTs /api/auth/onboarding/ to create a
/// tenant + its first admin, then pops back to login. The new tenant's slug is
/// shown so the operator knows what to set as X-Tenant-ID.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _orgName = TextEditingController();
  final _orgSlug = TextEditingController();
  final _orgAddress = TextEditingController();
  final _orgContact = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _pass = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _busy = false;
  bool _obscure = true;
  String? _error;
  List<Map<String, dynamic>> _jurisdictions = [];
  int? _stateId;
  int? _localId;

  // Cascade: states, then the locals under the picked state.
  Iterable<Map<String, dynamic>> get _states =>
      _jurisdictions.where((j) => j['level'] == 'state');
  Iterable<Map<String, dynamic>> get _locals =>
      _jurisdictions.where((j) => j['level'] == 'local' && j['parent'] == _stateId);

  @override
  void initState() {
    super.initState();
    // Best-effort: an empty/failed list just hides the optional picker.
    api.jurisdictions().then((j) {
      if (mounted) setState(() => _jurisdictions = j);
    }).catchError((_) {});
  }

  @override
  void dispose() {
    for (final c in [
      _orgName,
      _orgSlug,
      _orgAddress,
      _orgContact,
      _phone,
      _email,
      _pass,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await api.onboarding(
        orgName: _orgName.text.trim(),
        orgSlug: _orgSlug.text.trim(),
        orgAddress: _orgAddress.text.trim(),
        orgContact: _orgContact.text.trim(),
        phone: _phone.text.trim(),
        email: _email.text.trim(),
        password: _pass.text,
        jurisdictionId: _localId ?? _stateId,  // most specific picked
      );
      final slug = (res['tenant'] as Map?)?['slug'] ?? _orgSlug.text.trim();
      // Point the client at the tenant just created so the next login targets it.
      await setTenant(slug);
      if (!mounted) return;
      Navigator.of(context).pop();
      showSuccess(context,
          res['message'] as String? ?? 'Organization "$slug" created.');
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _field(TextEditingController c, String label, IconData icon,
      {TextInputType? type,
      bool obscure = false,
      Widget? suffix,
      String? Function(String?)? validator}) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: TextFormField(
        controller: c,
        keyboardType: type,
        obscureText: obscure,
        autocorrect: false,
        validator: validator,
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: Icon(icon),
          suffixIcon: suffix,
        ),
      ),
    );
  }

  Widget _jurisdictionDropdown({
    required String label,
    required int? value,
    required Iterable<Map<String, dynamic>> rows,
    required ValueChanged<int?> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: DropdownButtonFormField<int>(
        value: value,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: const Icon(Icons.account_tree_outlined),
        ),
        items: [
          for (final j in rows)
            DropdownMenuItem(
              value: j['id'] as int,
              child: Text(j['name'] as String, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: onChanged,
      ),
    );
  }

  String? _required(String? v) =>
      (v == null || v.trim().isEmpty) ? 'Required' : null;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        title: const Text('Register organization'),
      ),
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 420),
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Set up your clinic',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.outfit(
                            color: context.labelColor,
                            fontSize: 26,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Creates your organization and admin account',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(
                              color: context.subLabelColor, fontSize: 14),
                        ),
                        const SizedBox(height: 24),
                        GlassCard(
                          padding: const EdgeInsets.all(20),
                          child: Form(
                            key: _formKey,
                            child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _field(_orgName, 'Organization name',
                                  Icons.apartment_outlined,
                                  validator: _required),
                              _field(_orgSlug, 'Slug (e.g. demo-clinic)',
                                  Icons.tag_outlined, validator: (v) {
                                if (v == null || v.trim().isEmpty) {
                                  return 'Required';
                                }
                                if (!RegExp(r'^[a-z0-9-]+$').hasMatch(v.trim())) {
                                  return 'Lowercase letters, numbers, hyphens only';
                                }
                                return null;
                              }),
                              _field(_orgAddress, 'Address',
                                  Icons.location_on_outlined,
                                  type: TextInputType.streetAddress,
                                  validator: _required),
                              _field(_orgContact, 'Contact (phone or email)',
                                  Icons.contact_phone_outlined,
                                  validator: _required),
                              if (_states.isNotEmpty)
                                _jurisdictionDropdown(
                                  label: 'State (optional)',
                                  value: _stateId,
                                  rows: _states,
                                  onChanged: (v) => setState(() {
                                    _stateId = v;
                                    _localId = null;  // state changed, clear local
                                  }),
                                ),
                              if (_locals.isNotEmpty)
                                _jurisdictionDropdown(
                                  label: 'Local government (optional)',
                                  value: _localId,
                                  rows: _locals,
                                  onChanged: (v) => setState(() => _localId = v),
                                ),
                              const Divider(height: 32),
                              _field(_phone, 'Admin phone',
                                  Icons.phone_outlined,
                                  type: TextInputType.phone,
                                  validator: _required),
                              _field(_email, 'Admin email', Icons.mail_outline,
                                  type: TextInputType.emailAddress,
                                  validator: (v) {
                                if (v == null || v.trim().isEmpty) return null;
                                return v.contains('@')
                                    ? null
                                    : 'Enter a valid email';
                              }),
                              _field(_pass, 'Password', Icons.lock_outline,
                                  obscure: _obscure,
                                  validator: (v) =>
                                      (v == null || v.length < 8)
                                          ? 'At least 8 characters'
                                          : null,
                                  suffix: IconButton(
                                    icon: Icon(_obscure
                                        ? Icons.visibility_off
                                        : Icons.visibility),
                                    onPressed: () =>
                                        setState(() => _obscure = !_obscure),
                                  )),
                              if (_error != null)
                                Padding(
                                  padding: const EdgeInsets.only(top: 16),
                                  child: Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: EnhancedTheme.errorRed
                                          .withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(14),
                                      border: Border.all(
                                          color: EnhancedTheme.errorRed
                                              .withValues(alpha: 0.3)),
                                    ),
                                    child: Row(
                                      children: [
                                        const Icon(Icons.error_outline,
                                            color: EnhancedTheme.errorRed,
                                            size: 20),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: Text(_error!,
                                              style: const TextStyle(
                                                  color:
                                                      EnhancedTheme.errorRed)),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              const SizedBox(height: 24),
                              ElevatedButton(
                                onPressed: _busy ? null : _submit,
                                child: _busy
                                    ? const SizedBox(
                                        height: 20,
                                        width: 20,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white),
                                      )
                                    : const Text('Create organization'),
                              ),
                            ],
                          ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
