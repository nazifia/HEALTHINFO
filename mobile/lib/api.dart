import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'config.dart';

/// Thin REST client for the HEALTH INFO Django API.
/// Handles JWT storage, the X-Tenant-ID header, and one transparent
/// access-token refresh on 401.
class Api {
  String? _access;
  String? _refresh;

  static const _kAccess = 'access';
  static const _kRefresh = 'refresh';

  bool get isLoggedIn => _access != null;

  // Roles allowed to create/edit catalog content (mirrors backend WRITE_ROLES).
  static const writeRoles = {
    'super_admin',
    'tenant_admin',
    'doctor',
    'pharmacist',
  };

  String? _role;

  /// Current user's role, fetched once from /api/users/me/ then cached.
  /// ponytail: cache lives for the session; cleared on logout.
  Future<String?> myRole() async {
    if (_role != null) return _role;
    try {
      final r = await get('/api/users/me/');
      _role = (r as Map)['role']?.toString();
    } catch (_) {}
    return _role;
  }

  bool roleCanWrite(String? role) => writeRoles.contains(role);

  // Roles allowed to file/edit case + ADR reports (mirrors backend REPORT_ROLES).
  static const reportRoles = {...writeRoles, 'nurse'};

  bool roleCanReport(String? role) => reportRoles.contains(role);

  Future<void> loadTokens() async {
    final p = await SharedPreferences.getInstance();
    _access = p.getString(_kAccess);
    _refresh = p.getString(_kRefresh);
  }

  Future<void> _saveTokens() async {
    final p = await SharedPreferences.getInstance();
    if (_access != null) await p.setString(_kAccess, _access!);
    if (_refresh != null) await p.setString(_kRefresh, _refresh!);
  }

  Future<void> logout() async {
    // Best-effort: blacklist the refresh token server-side so it can't be
    // replayed. Never let a failed/offline call block the local clear.
    if (_refresh != null) {
      try {
        await http.post(
          _uri('/api/auth/logout/'),
          headers: _headers(auth: false, json: true),
          body: jsonEncode({'refresh': _refresh}),
        );
      } catch (_) {}
    }
    _access = null;
    _refresh = null;
    _role = null;
    final p = await SharedPreferences.getInstance();
    await p.remove(_kAccess);
    await p.remove(_kRefresh);
  }

  Map<String, String> _headers({bool auth = true, bool json = false}) {
    final h = <String, String>{'X-Tenant-ID': tenantSlug};
    if (json) h['Content-Type'] = 'application/json';
    if (auth && _access != null) h['Authorization'] = 'Bearer $_access';
    return h;
  }

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$apiBase$path').replace(queryParameters: query);

  /// POST /api/auth/token/ — obtain JWT pair.
  Future<void> login(String phone, String password) async {
    final r = await http.post(
      _uri('/api/auth/token/'),
      headers: _headers(auth: false, json: true),
      body: jsonEncode({'phone': phone, 'password': password}),
    );
    if (r.statusCode != 200) {
      throw ApiException('Login failed (${r.statusCode})', r.body);
    }
    final data = jsonDecode(r.body) as Map<String, dynamic>;
    _access = data['access'] as String?;
    _refresh = data['refresh'] as String?;
    await _saveTokens();
  }

  /// POST /api/auth/register/
  Future<void> register(String phone, String email, String password,
      {String username = ''}) async {
    final r = await http.post(
      _uri('/api/auth/register/'),
      headers: _headers(auth: false, json: true),
      body: jsonEncode({
        if (username.isNotEmpty) 'username': username,
        'phone': phone,
        'email': email,
        'password': password,
      }),
    );
    if (r.statusCode != 201) {
      throw ApiException('Register failed (${r.statusCode})', r.body);
    }
  }

  /// POST /api/auth/onboarding/ — self-serve org signup: creates a tenant and
  /// its first tenant_admin. Public (no auth). Returns the decoded response so
  /// the caller can grab the new tenant slug.
  Future<Map<String, dynamic>> onboarding({
    required String orgName,
    required String orgSlug,
    required String orgAddress,
    required String orgContact,
    required String phone,
    required String email,
    required String password,
    int? jurisdictionId,
  }) async {
    final r = await http.post(
      _uri('/api/auth/onboarding/'),
      headers: _headers(auth: false, json: true),
      body: jsonEncode({
        'org_name': orgName,
        'org_slug': orgSlug,
        'org_address': orgAddress,
        'org_contact': orgContact,
        'phone': phone,
        'email': email,
        'password': password,
        if (jurisdictionId != null) 'jurisdiction': jurisdictionId,
      }),
    );
    if (r.statusCode != 201) {
      throw ApiException('Onboarding failed (${r.statusCode})', r.body);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// GET /api/auth/onboarding/jurisdictions/ — public list for the signup
  /// picker. Returns rows of {id, name, level, parent}.
  Future<List<Map<String, dynamic>>> jurisdictions() async {
    final r = await http.get(
      _uri('/api/auth/onboarding/jurisdictions/'),
      headers: _headers(auth: false),
    );
    if (r.statusCode != 200) {
      throw ApiException('Jurisdictions failed (${r.statusCode})', r.body);
    }
    return (jsonDecode(r.body) as List).cast<Map<String, dynamic>>();
  }

  Future<bool> _refreshAccess() async {
    if (_refresh == null) return false;
    final r = await http.post(
      _uri('/api/auth/token/refresh/'),
      headers: _headers(auth: false, json: true),
      body: jsonEncode({'refresh': _refresh}),
    );
    if (r.statusCode != 200) return false;
    _access = (jsonDecode(r.body) as Map<String, dynamic>)['access'] as String?;
    await _saveTokens();
    return true;
  }

  /// Authenticated GET returning decoded JSON. Retries once after refresh on 401.
  Future<dynamic> get(String path, [Map<String, String>? query]) async {
    var r = await http.get(_uri(path, query), headers: _headers());
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await http.get(_uri(path, query), headers: _headers());
    }
    if (r.statusCode != 200) {
      throw ApiException('GET $path failed (${r.statusCode})', r.body);
    }
    return jsonDecode(r.body);
  }

  /// Authenticated POST returning decoded JSON. Retries once after refresh on 401.
  Future<dynamic> post(String path, [Map<String, dynamic>? body]) async {
    final headers = _headers(json: true);
    final payload = jsonEncode(body ?? {});
    var r = await http.post(_uri(path), headers: headers, body: payload);
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await http.post(_uri(path), headers: _headers(json: true), body: payload);
    }
    if (r.statusCode < 200 || r.statusCode >= 300) {
      throw ApiException('POST $path failed (${r.statusCode})', r.body);
    }
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  /// Authenticated PATCH returning decoded JSON. Retries once after refresh on 401.
  Future<dynamic> patch(String path, Map<String, dynamic> body) async {
    final payload = jsonEncode(body);
    var r = await http.patch(_uri(path), headers: _headers(json: true), body: payload);
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await http.patch(_uri(path), headers: _headers(json: true), body: payload);
    }
    if (r.statusCode < 200 || r.statusCode >= 300) {
      throw ApiException('PATCH $path failed (${r.statusCode})', r.body);
    }
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  /// DRF list endpoints paginate; unwrap to the row list either way.
  Future<List<dynamic>> getList(String path, [Map<String, String>? query]) async {
    final data = await get(path, query);
    if (data is Map && data.containsKey('results')) {
      return data['results'] as List<dynamic>;
    }
    return data as List<dynamic>;
  }
}

class ApiException implements Exception {
  final String message;
  final String body;
  ApiException(this.message, [this.body = '']);

  /// Human message for the UI: the backend envelope's {"message": ...} when
  /// present (see config/responses.py), else the generic caller fallback.
  String get friendly {
    try {
      final m = jsonDecode(body);
      if (m is Map && m['message'] is String) return m['message'] as String;
    } catch (_) {}
    return message;
  }

  @override
  String toString() => friendly;
}
