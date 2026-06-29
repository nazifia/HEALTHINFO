import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:shared_preferences/shared_preferences.dart';

// Backend connection settings.
// Web defaults to the deployed prod backend so `flutter build web` is safe
// without flags; Android emulator uses the 10.0.2.2 host alias. Override for
// local dev or a real device:
//   flutter run --dart-define=API_BASE=http://localhost:8000
const String _apiBaseOverride = String.fromEnvironment('API_BASE');
final String apiBase = _apiBaseOverride.isNotEmpty
    ? _apiBaseOverride
    : (kIsWeb ? 'https://healthinfo.pythonanywhere.com' : 'http://10.0.2.2:8000');

// Tenant slug sent as X-Tenant-ID header (see apps/tenants/middleware.py).
// Runtime value: the user picks their organization at login / onboarding, so a
// single build serves every tenant. TENANT dart-define is only the first-run
// default. Persisted in prefs and reloaded on launch via [loadTenant].
const String _tenantDefault = String.fromEnvironment(
  'TENANT',
  defaultValue: 'demo', // matches seed_dev's Demo Clinic tenant
);
String tenantSlug = _tenantDefault;

const String _kTenant = 'tenant_slug';

Future<void> loadTenant() async {
  final p = await SharedPreferences.getInstance();
  tenantSlug = p.getString(_kTenant) ?? _tenantDefault;
}

Future<void> setTenant(String slug) async {
  tenantSlug = slug.trim();
  final p = await SharedPreferences.getInstance();
  await p.setString(_kTenant, tenantSlug);
}

// Auto-logout after this much user inactivity (no taps/scrolls). Health data —
// keep it short. Override: --dart-define=IDLE_TIMEOUT_MINUTES=10
const int _idleMinutes = int.fromEnvironment('IDLE_TIMEOUT_MINUTES', defaultValue: 5);
const Duration idleTimeout = Duration(minutes: _idleMinutes);

// Direct APK download shown to web visitors. Firebase's free (Spark) plan
// forbids hosting .apk, so the file lives on GitHub Releases. Upload the built
// APK as an asset named `health-info.apk` on a release; this "latest" URL then
// always points at the newest one. Override if hosted elsewhere:
//   flutter build web --dart-define=APP_DOWNLOAD_URL=https://cdn.example.com/app.apk
const String appDownloadUrl = String.fromEnvironment(
  'APP_DOWNLOAD_URL',
  defaultValue: 'https://github.com/nazifia/HEALTHINFO/releases/latest/download/health-info.apk',
);
