// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;

// Direct APK install only works on Android. Hide the prompt elsewhere.
bool get isAndroidWeb =>
    html.window.navigator.userAgent.toLowerCase().contains('android');

// Anchor with an explicit `.apk` download name so Android saves it and the
// system installer recognizes it on tap. (The web can't trigger the install
// itself — Android blocks that; the user taps the downloaded file.)
void openUrl(String url) {
  final name = url.split('/').last.split('?').first;
  html.AnchorElement(href: url)
    ..download = name.endsWith('.apk') ? name : 'health-info.apk'
    ..click();
}
