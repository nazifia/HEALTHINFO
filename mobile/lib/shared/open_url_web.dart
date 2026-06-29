import 'dart:html' as html;

// Anchor with `download` so the APK saves to disk instead of the browser
// trying to navigate to / render it.
void openUrl(String url) {
  html.AnchorElement(href: url)
    ..download = ''
    ..target = '_blank'
    ..click();
}
