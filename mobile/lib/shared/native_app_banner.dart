import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/theme/enhanced_theme.dart';
import 'web_install_prompt.dart';

/// Wraps the app and, on web only, shows a dismissible bar prompting the
/// visitor to install the app as a PWA. Chrome/Edge/Android use the browser's
/// native install prompt; iOS Safari gets Add-to-Home-Screen instructions.
class NativeAppBanner extends StatefulWidget {
  const NativeAppBanner({super.key, required this.child});

  final Widget child;

  @override
  State<NativeAppBanner> createState() => _NativeAppBannerState();
}

class _NativeAppBannerState extends State<NativeAppBanner> {
  static const _prefKey = 'install_banner_dismissed';
  bool _dismissed = true; // hidden until prefs load
  bool _promptReady = false;

  @override
  void initState() {
    super.initState();
    if (!kIsWeb) return;
    SharedPreferences.getInstance().then((prefs) {
      if (mounted) {
        setState(() => _dismissed = prefs.getBool(_prefKey) ?? false);
      }
    });
    initInstallPrompt(() {
      if (mounted) setState(() => _promptReady = true);
    });
  }

  Future<void> _dismiss() async {
    setState(() => _dismissed = true);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_prefKey, true);
  }

  void _install() {
    promptInstall();
    _dismiss(); // user accepted or dismissed the browser dialog
  }

  void _showIosInstructions() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => const _IosInstallSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb || _dismissed || isInstalledAsPwa()) return widget.child;

    final canInstall = _promptReady && canPromptInstall();
    final ios = isIosBrowser();
    if (!canInstall && !ios) return widget.child;

    return Column(
      children: [
        SafeArea(
          bottom: false,
          child: Container(
            width: double.infinity,
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [Color(0xFF1E3A5F), EnhancedTheme.primaryTeal],
              ),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(children: [
              const Icon(Icons.install_mobile, color: Colors.white, size: 18),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Install the app for a faster, more secure experience.',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: canInstall ? _install : _showIosInstructions,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: Colors.white.withValues(alpha: 0.4)),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(
                      canInstall ? Icons.download_rounded : Icons.info_outline,
                      color: Colors.white,
                      size: 13,
                    ),
                    const SizedBox(width: 5),
                    Text(
                      canInstall ? 'Install' : 'How to install',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ]),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: _dismiss,
                child: const Icon(Icons.close, color: Colors.white60, size: 18),
              ),
            ]),
          ),
        ),
        Expanded(child: widget.child),
      ],
    );
  }
}

// ── iOS install instructions sheet ────────────────────────────────────────────

class _IosInstallSheet extends StatelessWidget {
  const _IosInstallSheet();

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
          decoration: BoxDecoration(
            color: const Color(0xFF1E293B).withValues(alpha: 0.95),
            border: Border(
              top: BorderSide(color: Colors.white.withValues(alpha: 0.15), width: 1.5),
            ),
          ),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            const Row(children: [
              Icon(Icons.install_mobile, color: EnhancedTheme.primaryTeal, size: 24),
              SizedBox(width: 10),
              Text(
                'Install the app',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ]),
            const SizedBox(height: 20),
            const _IosStep(
              step: 1,
              icon: Icons.ios_share,
              text: 'Tap the Share button at the bottom of Safari',
            ),
            const SizedBox(height: 14),
            const _IosStep(
              step: 2,
              icon: Icons.add_box_outlined,
              text: 'Scroll down and tap "Add to Home Screen"',
            ),
            const SizedBox(height: 14),
            const _IosStep(
              step: 3,
              icon: Icons.check_circle_outline,
              text: 'Tap "Add" — the app icon will appear on your home screen',
            ),
          ]),
        ),
      ),
    );
  }
}

class _IosStep extends StatelessWidget {
  final int step;
  final IconData icon;
  final String text;

  const _IosStep({required this.step, required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        width: 24,
        height: 24,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: EnhancedTheme.primaryTeal.withValues(alpha: 0.25),
          shape: BoxShape.circle,
          border: Border.all(color: EnhancedTheme.primaryTeal, width: 1),
        ),
        child: Text(
          '$step',
          style: const TextStyle(
            color: EnhancedTheme.primaryTeal,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      const SizedBox(width: 12),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Row(children: [
            Icon(icon, color: Colors.white70, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(color: Colors.white, fontSize: 13),
              ),
            ),
          ]),
        ),
      ),
    ]);
  }
}
