import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';
import 'open_url_stub.dart' if (dart.library.html) 'open_url_web.dart';

const _kDismissed = 'native_app_banner_dismissed';

/// Wraps the app and, on web only, shows a one-line dismissible bar suggesting
/// the visitor install the native app. Dismissal is remembered across visits.
class NativeAppBanner extends StatefulWidget {
  const NativeAppBanner({super.key, required this.child});

  final Widget child;

  @override
  State<NativeAppBanner> createState() => _NativeAppBannerState();
}

class _NativeAppBannerState extends State<NativeAppBanner> {
  bool _show = false;

  @override
  void initState() {
    super.initState();
    if (kIsWeb && isAndroidWeb) _load();
  }

  Future<void> _load() async {
    final p = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() => _show = !(p.getBool(_kDismissed) ?? false));
  }

  void _install() {
    openUrl(appDownloadUrl);
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Installing the app'),
        content: const Text(
          'The app file (.apk) is downloading.\n\n'
          '1. Open it from your notifications or Downloads.\n'
          '2. If prompted, allow installs from this source.\n'
          '3. Tap Install.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }

  Future<void> _dismiss() async {
    setState(() => _show = false);
    final p = await SharedPreferences.getInstance();
    await p.setBool(_kDismissed, true);
  }

  @override
  Widget build(BuildContext context) {
    if (!_show) return widget.child;
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        Material(
          color: scheme.primaryContainer,
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                children: [
                  Icon(Icons.install_mobile, color: scheme.onPrimaryContainer, size: 20),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Get the app for a faster, more secure experience.',
                      style: TextStyle(color: scheme.onPrimaryContainer),
                    ),
                  ),
                  TextButton(
                    onPressed: _install,
                    child: const Text('Install'),
                  ),
                  IconButton(
                    tooltip: 'Dismiss',
                    icon: Icon(Icons.close, color: scheme.onPrimaryContainer, size: 20),
                    onPressed: _dismiss,
                  ),
                ],
              ),
            ),
          ),
        ),
        Expanded(child: widget.child),
      ],
    );
  }
}
