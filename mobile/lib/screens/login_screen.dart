import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../config.dart';
import '../l10n/app_localizations.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import 'home_screen.dart';
import 'onboarding_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phone = TextEditingController();
  final _pass = TextEditingController();
  final _email = TextEditingController();
  final _username = TextEditingController();
  final _tenant = TextEditingController(text: tenantSlug);
  bool _registerMode = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _phone.dispose();
    _pass.dispose();
    _email.dispose();
    _username.dispose();
    _tenant.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final slug = _tenant.text.trim();
      if (slug.isEmpty) {
        setState(() => _error = 'Enter your organization slug');
        return;
      }
      await setTenant(slug);
      if (_registerMode) {
        await api.register(_phone.text.trim(), _email.text.trim(), _pass.text,
            username: _username.text.trim());
      }
      await api.login(_phone.text.trim(), _pass.text);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const HomeScreen()),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
      showError(context, e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: context.scaffoldBg,
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
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Hero brand header
                        Center(
                          child: Container(
                            height: 96,
                            width: 96,
                            margin: const EdgeInsets.only(bottom: 24),
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                                colors: [
                                  EnhancedTheme.primaryTeal,
                                  EnhancedTheme.accentCyan,
                                ],
                              ),
                              borderRadius: BorderRadius.circular(28),
                              boxShadow: [
                                BoxShadow(
                                  color: EnhancedTheme.primaryTeal
                                      .withValues(alpha: 0.35),
                                  blurRadius: 24,
                                  offset: const Offset(0, 8),
                                ),
                              ],
                            ),
                            child: const Icon(Icons.health_and_safety,
                                size: 52, color: Colors.white),
                          ),
                        ),
                        Text(
                          'Health Info',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.outfit(
                            color: context.labelColor,
                            fontSize: 30,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _registerMode
                              ? 'Create your account'
                              : 'Welcome back, sign in to continue',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(
                              color: context.subLabelColor, fontSize: 14),
                        ),
                        const SizedBox(height: 28),
                        GlassCard(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              // Sign in / Register toggle
                              SegmentedButton<bool>(
                                segments: [
                                  ButtonSegment(
                                      value: false, label: Text(t.signIn)),
                                  ButtonSegment(
                                      value: true, label: Text(t.register)),
                                ],
                                selected: {_registerMode},
                                onSelectionChanged: _busy
                                    ? null
                                    : (s) =>
                                        setState(() => _registerMode = s.first),
                              ),
                              const SizedBox(height: 20),
                              TextField(
                                controller: _tenant,
                                decoration: const InputDecoration(
                                  labelText: 'Organization slug',
                                  prefixIcon: Icon(Icons.tag_outlined),
                                ),
                                autocorrect: false,
                              ),
                              const SizedBox(height: 12),
                              TextField(
                                controller: _phone,
                                decoration: const InputDecoration(
                                  labelText: 'Phone number',
                                  prefixIcon: Icon(Icons.phone_outlined),
                                ),
                                keyboardType: TextInputType.phone,
                                autocorrect: false,
                              ),
                              if (_registerMode) ...[
                                const SizedBox(height: 12),
                                TextField(
                                  controller: _username,
                                  decoration: const InputDecoration(
                                    labelText: 'Display name',
                                    prefixIcon: Icon(Icons.person_outline),
                                  ),
                                  textCapitalization: TextCapitalization.words,
                                ),
                                const SizedBox(height: 12),
                                TextField(
                                  controller: _email,
                                  decoration: const InputDecoration(
                                    labelText: 'Email',
                                    prefixIcon: Icon(Icons.mail_outline),
                                  ),
                                  keyboardType: TextInputType.emailAddress,
                                ),
                              ],
                              const SizedBox(height: 12),
                              TextField(
                                controller: _pass,
                                decoration: InputDecoration(
                                  labelText: t.passwordLabel,
                                  prefixIcon: const Icon(Icons.lock_outline),
                                  suffixIcon: IconButton(
                                    icon: Icon(_obscure
                                        ? Icons.visibility_off
                                        : Icons.visibility),
                                    onPressed: () =>
                                        setState(() => _obscure = !_obscure),
                                  ),
                                ),
                                obscureText: _obscure,
                              ),
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
                                    : Text(_registerMode
                                        ? t.register
                                        : t.signIn),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextButton(
                          onPressed: _busy
                              ? null
                              : () => Navigator.of(context).push(
                                    MaterialPageRoute(
                                        builder: (_) => const OnboardingScreen()),
                                  ),
                          child: const Text('Register your organization'),
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
