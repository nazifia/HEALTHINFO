import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';

/// The uid and token out of a pasted reset link, or null when it is not one.
///
/// The link points at the web client and carries its payload in the fragment
/// (`https://host/#/reset?uid=..&token=..`), so the pair has to be read off
/// `Uri.fragment` — `queryParameters` sees nothing after a `#`. Pasting just
/// the `uid=..&token=..` tail works too, because a patient copying out of a
/// mail app rarely gets the selection exactly right.
Map<String, String>? parseResetLink(String pasted) {
  final text = pasted.trim();
  if (text.isEmpty) return null;
  final fragment = Uri.tryParse(text)?.fragment ?? '';
  final source = fragment.isNotEmpty ? fragment : text;
  final query = source.contains('?') ? source.split('?').last : source;
  final parts = Uri.splitQueryString(query);
  final uid = parts['uid'] ?? '';
  final token = parts['token'] ?? '';
  if (uid.isEmpty || token.isEmpty) return null;
  return {'uid': uid, 'token': token};
}

/// Forgotten password, in two steps on one screen: ask for a link by phone,
/// then paste that link back in with a new password.
///
/// Deliberately no deep link. The mailed link opens the web client, and this
/// screen takes the same link pasted in, so the flow works before anyone
/// configures URL handling on either platform.
/// ponytail: add an app link (android:autoVerify / associated domains) only
/// when the paste step is measurably costing patients the reset.
class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _phone = TextEditingController();
  final _link = TextEditingController();
  final _pass = TextEditingController();

  // False while asking for a link, true once one has been sent — or when the
  // patient already has one and taps straight through.
  bool _hasLink = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _phone.dispose();
    _link.dispose();
    _pass.dispose();
    super.dispose();
  }

  Future<void> _run(Future<String> Function() call, {bool done = false}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final message = await call();
      if (!mounted) return;
      showSuccess(context, message);
      if (done) {
        Navigator.of(context).pop();
      } else {
        setState(() => _hasLink = true);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
      showError(context, e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _send() {
    final phone = _phone.text.trim();
    if (phone.isEmpty) {
      setState(() => _error = 'Enter the phone number you sign in with.');
      return;
    }
    _run(() => api.passwordReset(phone));
  }

  void _confirm() {
    final parts = parseResetLink(_link.text);
    if (parts == null) {
      setState(() => _error = 'That does not look like the reset link. Paste '
          'the whole link from the email.');
      return;
    }
    if (_pass.text.isEmpty) {
      setState(() => _error = 'Choose a new password.');
      return;
    }
    _run(
      () => api.passwordResetConfirm(parts['uid']!, parts['token']!, _pass.text),
      done: true,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Forgot password'),
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
                          _hasLink
                              ? 'Paste the link from your email and choose a '
                                  'new password'
                              : 'We will email a reset link to the address on '
                                  'your account',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(
                              color: context.subLabelColor, fontSize: 14),
                        ),
                        const SizedBox(height: 20),
                        GlassCard(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              if (!_hasLink)
                                TextField(
                                  controller: _phone,
                                  decoration: const InputDecoration(
                                    labelText: 'Phone',
                                    hintText: '08031234567',
                                    prefixIcon: Icon(Icons.phone_outlined),
                                  ),
                                  keyboardType: TextInputType.phone,
                                  autocorrect: false,
                                )
                              else ...[
                                TextField(
                                  controller: _link,
                                  decoration: const InputDecoration(
                                    labelText: 'Reset link from the email',
                                    prefixIcon: Icon(Icons.link_outlined),
                                  ),
                                  maxLines: 2,
                                  autocorrect: false,
                                ),
                                const SizedBox(height: 12),
                                TextField(
                                  controller: _pass,
                                  decoration: InputDecoration(
                                    labelText: 'New password',
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
                                const SizedBox(height: 8),
                                Text(
                                  'The link stops working 30 minutes after it '
                                  'is sent.',
                                  style: GoogleFonts.inter(
                                      color: context.subLabelColor,
                                      fontSize: 12),
                                ),
                              ],
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
                                onPressed: _busy
                                    ? null
                                    : (_hasLink ? _confirm : _send),
                                child: _busy
                                    ? const SizedBox(
                                        height: 20,
                                        width: 20,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white),
                                      )
                                    : Text(_hasLink
                                        ? 'Save password'
                                        : 'Send reset link'),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextButton(
                          onPressed: _busy
                              ? null
                              : () => setState(() {
                                    _hasLink = !_hasLink;
                                    _error = null;
                                  }),
                          child: Text(_hasLink
                              ? 'Send another link'
                              : 'I already have a link'),
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
