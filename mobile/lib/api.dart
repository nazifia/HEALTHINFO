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

  Map<String, dynamic>? _me;

  /// Current user, fetched once from /api/users/me/ then cached.
  /// ponytail: cache lives for the session; cleared on logout.
  Future<Map<String, dynamic>?> me() async {
    if (_me != null) return _me;
    try {
      final r = await get('/api/users/me/');
      _me = (r as Map).cast<String, dynamic>();
    } catch (_) {}
    return _me;
  }

  /// Current user's role — what the screens gate on.
  Future<String?> myRole() async => (await me())?['role']?.toString();

  /// Current user's id, for "did I raise this?" checks on rows that name a
  /// user (a payment request's dispenser, a sale's server).
  Future<int?> myId() async => (await me())?['id'] as int?;

  bool roleCanWrite(String? role) => writeRoles.contains(role);

  // Roles allowed to register/edit patients and file clinical records
  // (mirrors backend REPORT_ROLES: the nursing cadres write clinically too).
  static const reportRoles = {...writeRoles, 'nurse', 'midwife', 'chew'};

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
    _me = null;
    final p = await SharedPreferences.getInstance();
    await p.remove(_kAccess);
    await p.remove(_kRefresh);
  }

  Map<String, String> _headers({
    bool auth = true,
    bool json = false,
    bool tenant = true,
  }) {
    // Sign-in is the one call sent with no tenant: the stored slug may belong
    // to whoever used this device last, and the server resolves the user's own
    // organization (or the host's) instead.
    final h = tenant ? <String, String>{'X-Tenant-ID': tenantSlug} : <String, String>{};
    if (json) h['Content-Type'] = 'application/json';
    if (auth && _access != null) h['Authorization'] = 'Bearer $_access';
    return h;
  }

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$apiBase$path').replace(queryParameters: query);

  /// Nigerian mobile numbers, or the last-6-digit pharmacy short login;
  /// anything else is treated as a licence number.
  static final _phonePattern = RegExp(r'^(?:(?:\+234|0)[789]\d{9}|\d{6})$');

  /// POST /api/auth/token/ — obtain JWT pair.
  ///
  /// [identifier] is a phone number (pharmacy staff: its last 6 digits), or a
  /// licence number for the clinical cadres (doctor, nurse, midwife, CHEW) who
  /// sign in with theirs instead.
  Future<void> login(String identifier, String password) async {
    final field = _phonePattern.hasMatch(identifier.replaceAll(' ', ''))
        ? 'phone'
        : 'license_number';
    final r = await http.post(
      _uri('/api/auth/token/'),
      headers: _headers(auth: false, json: true, tenant: false),
      body: jsonEncode({field: identifier, 'password': password}),
    );
    if (r.statusCode != 200) {
      throw ApiException('Login failed (${r.statusCode})', r.body);
    }
    final data = jsonDecode(r.body) as Map<String, dynamic>;
    _access = data['access'] as String?;
    _refresh = data['refresh'] as String?;
    await _saveTokens();
    // The token names the user's organization; every later call carries it.
    // Super-admins come back with none and keep whatever slug was set.
    final slug = (data['tenant'] as String?) ?? '';
    if (slug.isNotEmpty) {
      await setTenant(slug, name: (data['tenant_name'] as String?) ?? '');
    }
  }

  /// GET /api/auth/register/organizations/ — public signup picker.
  ///
  /// Someone without an account has no tenant to detect, so they choose one.
  /// Sent with no tenant header: the stored slug may be another user's.
  Future<List<Map<String, dynamic>>> organizations() async {
    final r = await http.get(
      _uri('/api/auth/register/organizations/'),
      headers: _headers(auth: false, tenant: false),
    );
    if (r.statusCode != 200) {
      throw ApiException('Could not load organizations (${r.statusCode})', r.body);
    }
    return (jsonDecode(r.body) as List).cast<Map<String, dynamic>>();
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

  /// Authenticated GET returning the raw body bytes. Retries once after refresh
  /// on 401, exactly as [get] does.
  ///
  /// For the endpoints that answer a file rather than JSON — the CSV exports —
  /// so the bytes reach the share sheet without going through jsonDecode.
  Future<List<int>> getBytes(String path, [Map<String, String>? query]) async {
    var r = await http.get(_uri(path, query), headers: _headers());
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await http.get(_uri(path, query), headers: _headers());
    }
    if (r.statusCode != 200) {
      throw ApiException('GET $path failed (${r.statusCode})', r.body);
    }
    return r.bodyBytes;
  }

  /// Authenticated POST returning decoded JSON. Retries once after refresh on 401.
  ///
  /// [body] is usually a map, but a few endpoints take a bare JSON list — the
  /// stocktake's count sheet, for one — so anything encodable travels.
  Future<dynamic> post(String path, [Object? body]) async {
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
