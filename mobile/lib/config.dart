import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:shared_preferences/shared_preferences.dart';

// Backend connection settings.
// Web defaults to the deployed prod backend so `flutter build web` is safe
// without flags; Android emulator uses the 10.0.2.2 host alias. Override for
// local dev or a real device:
//   flutter run --dart-define=API_BASE=http://localhost:8000
const String _apiBaseOverride = String.fromEnvironment('API_BASE');

String _defaultApiBase() {
  if (_apiBaseOverride.isNotEmpty) return _apiBaseOverride;
  if (kIsWeb) {
    // Served from a dev host → local backend; deployed host → prod API.
    final host = Uri.base.host;
    if (host == 'localhost' || host == '127.0.0.1') return 'http://$host:8000';
    return 'https://healthinfo.pythonanywhere.com';
  }
  return 'http://10.0.2.2:8000'; // Android emulator alias for the host machine
}

final String apiBase = _defaultApiBase();

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
