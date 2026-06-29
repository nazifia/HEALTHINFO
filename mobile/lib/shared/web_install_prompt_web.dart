// ignore: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:html' as html;
// ignore: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:js' as js;

html.Event? _deferredPrompt;
bool _promptAvailable = false;

/// Call once on app start. [onPromptReady] fires when the browser is ready
/// to show the install prompt (Chrome/Edge/Android Chrome).
void initInstallPrompt(void Function() onPromptReady) {
  if (isInstalledAsPwa()) return;

  html.window.addEventListener('beforeinstallprompt', (event) {
    event.preventDefault();
    _deferredPrompt = event;
    _promptAvailable = true;
    onPromptReady();
  });

  // Clear prompt state if the app gets installed via another path.
  html.window.addEventListener('appinstalled', (_) {
    _deferredPrompt = null;
    _promptAvailable = false;
  });
}

/// True when [promptInstall] can be called (Chrome / Edge / Android Chrome).
bool canPromptInstall() => _promptAvailable;

/// True when running on iOS Safari (no beforeinstallprompt support).
bool isIosBrowser() {
  final ua = html.window.navigator.userAgent.toLowerCase();
  final isIos = ua.contains('iphone') || ua.contains('ipad') || ua.contains('ipod');
  final isSafari = ua.contains('safari') && !ua.contains('chrome');
  return isIos && isSafari;
}

/// True when the app is already running as an installed PWA.
bool isInstalledAsPwa() {
  try {
    return html.window.matchMedia('(display-mode: standalone)').matches;
  } catch (_) {
    return false;
  }
}

/// Triggers the browser's native install prompt.
void promptInstall() {
  final prompt = _deferredPrompt;
  if (prompt == null) return;
  js.JsObject.fromBrowserObject(prompt).callMethod('prompt', []);
  _deferredPrompt = null;
  _promptAvailable = false;
}
