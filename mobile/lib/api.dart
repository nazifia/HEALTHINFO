import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'config.dart';

/// Thin REST client for the HEALTH INFO Django API.
/// Handles JWT storage, the X-Tenant-ID header, and one transparent
/// access-token refresh on 401.
class Api {
  // One client for every call. `http.get` and friends open a fresh connection
  // each time and close it; on a phone that is a TCP + TLS handshake per
  // request, which is most of the wait on a list screen firing several.
  final http.Client _http;

  /// [client] is only for tests, which hand in a MockClient.
  Api({http.Client? client}) : _http = client ?? http.Client();

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
  Future<Map<String, dynamic>?>? _meInFlight;

  /// Current user, fetched once from /api/users/me/ then cached.
  /// ponytail: cache lives for the session; cleared on logout.
  ///
  /// Start-up asks for the user from several places at once — main(), the
  /// drawer's role lookup, whichever screen opens first — so the in-flight
  /// request is shared. Without that they each fire their own GET and the
  /// screen waits on the slowest.
  Future<Map<String, dynamic>?> me() {
    if (_me != null) return Future.value(_me);
    return _meInFlight ??= _fetchMe().whenComplete(() => _meInFlight = null);
  }

  Future<Map<String, dynamic>?> _fetchMe() async {
    try {
      final r = await get('/api/users/me/');
      _me = (r as Map).cast<String, dynamic>();
      // The tenant sets how long an unattended screen may sit signed in. It
      // rides on the user, so arm the watcher from here rather than making
      // every caller remember to.
      final mins = _me?['idle_logout_minutes'];
      if (mins is int) idleMinutes.value = mins;
    } catch (_) {}
    return _me;
  }

  /// Forget the cached user so the next [me] re-reads it — after a profile
  /// edit, or after the organization's idle timeout changes.
  void forgetMe() {
    _me = null;
    _meInFlight = null;
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
        await _http.post(
          _uri('/api/auth/logout/'),
          headers: _headers(auth: false, json: true),
          body: jsonEncode({'refresh': _refresh}),
        );
      } catch (_) {}
    }
    _access = null;
    _refresh = null;
    _me = null;
    _meInFlight = null;
    idleMinutes.value = idleMinutesDefault;
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
    final r = await _http.post(
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
    // A super-admin comes back with none, and that empty slug is stored too:
    // they start outside every organization instead of inheriting the slug of
    // whoever used this device last, and they open one deliberately.
    final slug = (data['tenant'] as String?) ?? '';
    await setTenant(slug, name: (data['tenant_name'] as String?) ?? '');
  }

  /// GET /api/auth/register/organizations/ — public signup picker.
  ///
  /// Someone without an account has no tenant to detect, so they choose one.
  /// Sent with no tenant header: the stored slug may be another user's.
  Future<List<Map<String, dynamic>>> organizations() async {
    final r = await _http.get(
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
    final r = await _http.post(
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

  /// POST /api/auth/password-reset/ — mail a link for a forgotten password.
  ///
  /// No tenant header: someone locked out may have another user's slug stored,
  /// and the lookup is by phone, which is unique across the whole table.
  /// Returns the envelope message, which reads the same whether or not the
  /// number is known — the endpoint never confirms an account exists, so this
  /// screen must not either.
  Future<String> passwordReset(String phone) async {
    final r = await _http.post(
      _uri('/api/auth/password-reset/'),
      headers: _headers(auth: false, json: true, tenant: false),
      body: jsonEncode({'phone': phone}),
    );
    if (r.statusCode != 200) {
      throw ApiException('Could not send the reset link (${r.statusCode})', r.body);
    }
    return _message(r.body);
  }

  /// POST /api/auth/password-reset/confirm/ — set a new password from the uid
  /// and token carried by the mailed link.
  Future<String> passwordResetConfirm(
      String uid, String token, String password) async {
    final r = await _http.post(
      _uri('/api/auth/password-reset/confirm/'),
      headers: _headers(auth: false, json: true, tenant: false),
      body: jsonEncode({'uid': uid, 'token': token, 'password': password}),
    );
    if (r.statusCode != 200) {
      throw ApiException('Could not change the password (${r.statusCode})', r.body);
    }
    return _message(r.body);
  }

  /// The envelope's human message (see config/responses.py), or ''.
  String _message(String body) {
    final m = jsonDecode(body);
    return m is Map && m['message'] is String ? m['message'] as String : '';
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
    final r = await _http.post(
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
        'jurisdiction': ?jurisdictionId,
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
    final r = await _http.get(
      _uri('/api/auth/onboarding/jurisdictions/'),
      headers: _headers(auth: false),
    );
    if (r.statusCode != 200) {
      throw ApiException('Jurisdictions failed (${r.statusCode})', r.body);
    }
    return (jsonDecode(r.body) as List).cast<Map<String, dynamic>>();
  }

  /// Parallel calls that all see 401 share one refresh. Separate refreshes
  /// race token rotation and can blacklist each other, signing the user out
  /// mid-screen.
  Future<bool> _refreshAccess() =>
      _refreshing ??= _doRefresh().whenComplete(() => _refreshing = null);

  Future<bool>? _refreshing;

  Future<bool> _doRefresh() async {
    if (_refresh == null) return false;
    final r = await _http.post(
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
    var r = await _http.get(_uri(path, query), headers: _headers());
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await _http.get(_uri(path, query), headers: _headers());
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
    var r = await _http.get(_uri(path, query), headers: _headers());
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await _http.get(_uri(path, query), headers: _headers());
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
    var r = await _http.post(_uri(path), headers: headers, body: payload);
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await _http.post(_uri(path), headers: _headers(json: true), body: payload);
    }
    if (r.statusCode < 200 || r.statusCode >= 300) {
      throw ApiException('POST $path failed (${r.statusCode})', r.body);
    }
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  /// Authenticated PATCH returning decoded JSON. Retries once after refresh on 401.
  Future<dynamic> patch(String path, Map<String, dynamic> body) async {
    final payload = jsonEncode(body);
    var r = await _http.patch(_uri(path), headers: _headers(json: true), body: payload);
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await _http.patch(_uri(path), headers: _headers(json: true), body: payload);
    }
    if (r.statusCode < 200 || r.statusCode >= 300) {
      throw ApiException('PATCH $path failed (${r.statusCode})', r.body);
    }
    return r.body.isEmpty ? null : jsonDecode(r.body);
  }

  /// Authenticated DELETE. Retries once after refresh on 401.
  ///
  /// The endpoints that take one answer 204 with an empty body, so nothing is
  /// decoded — a caller that still needs the row keeps its own copy.
  Future<void> delete(String path) async {
    var r = await _http.delete(_uri(path), headers: _headers());
    if (r.statusCode == 401 && await _refreshAccess()) {
      r = await _http.delete(_uri(path), headers: _headers());
    }
    if (r.statusCode < 200 || r.statusCode >= 300) {
      throw ApiException('DELETE $path failed (${r.statusCode})', r.body);
    }
  }

  /// DRF list endpoints paginate; unwrap to the row list either way.
  Future<List<dynamic>> getList(String path, [Map<String, String>? query]) async {
    final data = await get(path, query);
    if (data is Map && data.containsKey('results')) {
      return data['results'] as List<dynamic>;
    }
    return data as List<dynamic>;
  }

  // --- patient portal ---------------------------------------------------
  // A patient reading their own record. No patient id is ever sent: the API
  // reads it off the signed-in account (apps.patients.portal), so these calls
  // cannot reach anybody else's record.

  /// GET /api/portal/me/ — the signed-in patient's details.
  Future<Map<String, dynamic>> portalMe() async =>
      (await get('/api/portal/me/') as Map).cast<String, dynamic>();

  /// GET /api/portal/medications/ — everything prescribed to them, newest
  /// first. [status] narrows it; 'prescribed' is what is still to collect.
  Future<List<dynamic>> portalMedications([String? status]) =>
      getList('/api/portal/medications/',
          {'status': ?status});

  /// GET /api/portal/history/ — the whole timeline, grouped by record type.
  Future<Map<String, dynamic>> portalHistory() async =>
      (await get('/api/portal/history/') as Map).cast<String, dynamic>();

  /// GET /api/portal/pharmacies/ — where a script can be filled, nearest
  /// first when the device shares a position. [medication] is a catalog
  /// medication id: pass it to see only the sites holding that drug.
  Future<List<dynamic>> portalPharmacies({
    double? lat,
    double? lng,
    Object? medication,
  }) {
    final located = lat != null && lng != null;
    return getList('/api/portal/pharmacies/', {
      if (located) 'lat': lat.toStringAsFixed(6),
      if (located) 'lng': lng.toStringAsFixed(6),
      if (medication != null) 'medication': '$medication',
    });
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
