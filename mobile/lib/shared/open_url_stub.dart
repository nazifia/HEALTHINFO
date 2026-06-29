// ponytail: stub for non-web targets. The native-app banner only renders on
// web, so this is never actually called off the web.
void openUrl(String url) {}

// Off the web there is no browser to detect, and the banner is gated on kIsWeb
// anyway, so report false.
bool get isAndroidWeb => false;
