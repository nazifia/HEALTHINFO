import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Start-up asks who the user is from several places at once. One request
/// should answer all of them, and the cache should answer everything after.
void main() {
  test('concurrent me() callers share one /api/users/me/ request', () async {
    var calls = 0;
    final api = Api(client: MockClient((_) async {
      calls++;
      await Future<void>.delayed(const Duration(milliseconds: 10));
      return http.Response(
          jsonEncode({'id': 7, 'role': 'doctor'}), 200,
          headers: {'content-type': 'application/json'});
    }));

    final me = api.me();
    final role = api.myRole();
    final id = api.myId();
    await Future.wait<dynamic>([me, role, id]);

    expect(calls, 1);
    expect(await role, 'doctor');
    expect(await id, 7);

    await api.me(); // cached from here on
    expect(calls, 1);

    api.forgetMe();
    await api.me();
    expect(calls, 2);
  });
}
