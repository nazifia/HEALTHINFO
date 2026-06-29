// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;

// Direct APK install only works on Android. Hide the prompt elsewhere.
bool get isAndroidWeb =>
    html.window.navigator.userAgent.toLowerCase().contains('android');

// Anchor with `download` so the APK saves to disk instead of the browser
// trying to navigate to / render it.
void openUrl(String url) {
  html.AnchorElement(href: url)
    ..download = ''
    ..target = '_blank'
    ..click();
}
