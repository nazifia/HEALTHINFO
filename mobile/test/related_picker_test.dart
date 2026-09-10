import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A picker holds the whole list, so it has to read the whole list.
///
/// api.getList answers one page, which left every relation picker offering the
/// first 25 rows: the disease, supplier or scheme someone actually needed was
/// unreachable, and the field it fills is a foreign key nobody can type
/// around. api.getAll pages instead. Mirrors the web fix in web/app.js.
void main() {
  final api = Api();

  /// Serves `total` rows, 100 to a page, and records what was asked for.
  MockClient pagedRows(int total, List<Uri> seen) => MockClient((req) async {
        seen.add(req.url);
        final page = int.parse(req.url.queryParameters['page'] ?? '1');
        final size = int.parse(req.url.queryParameters['page_size'] ?? '25');
        final start = (page - 1) * size;
        final rows = [
          for (var i = start; i < start + size && i < total; i++)
            {'id': i + 1, 'name': 'Row ${i + 1}'}
        ];
        return http.Response(
          jsonEncode({
            'count': total,
            'next': start + size < total ? 'p${page + 1}' : null,
            'results': rows,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

  test('getAll pages past the first page', () async {
    final seen = <Uri>[];
    final rows = await http.runWithClient(
        () => api.getAll('/api/diseases/'), () => pagedRows(250, seen));
    expect(rows.length, 250);
    expect(rows.last['id'], 250);
    expect(seen.length, 3, reason: 'stopped early or kept asking past the end');
    expect(seen.first.queryParameters['page_size'], '100',
        reason: 'asking for 25 at a time is 10 round trips, not 3');
  });

  test('getAll keeps the caller\'s own filter on every page', () async {
    final seen = <Uri>[];
    await http.runWithClient(
        () => api.getAll('/api/pharmacy/suppliers/', {'is_active': 'true'}),
        () => pagedRows(150, seen));
    expect(seen.every((u) => u.queryParameters['is_active'] == 'true'), isTrue);
  });

  test('getAll gives up rather than paging forever', () async {
    // A server that always says there is more: 10 pages of 100 and no further.
    final seen = <Uri>[];
    final rows = await http.runWithClient(
        () => api.getAll('/api/medications/'), () => pagedRows(5000, seen));
    expect(seen.length, 10);
    expect(rows.length, 1000);
  });

  test('an endpoint that does not paginate answers its rows as they are',
      () async {
    final client = MockClient((req) async => http.Response(
        jsonEncode([
          {'id': 1}
        ]),
        200,
        headers: {'content-type': 'application/json'}));
    final rows =
        await http.runWithClient(() => api.getAll('/api/x/'), () => client);
    expect(rows.length, 1);
  });

  test('the relation pickers read the whole list, the browse lists still page',
      () {
    String src(String p) => File(p).readAsStringSync();
    // Every field that fills a foreign key from a list held in the client.
    for (final entry in {
      'lib/screens/cases_screen.dart': 'api.getAll(path)',
      'lib/screens/consultations_screen.dart': "api.getAll('/api/diseases/')",
      'lib/screens/lab_results_screen.dart': "api.getAll('/api/lab-tests/')",
      'lib/screens/differential_screen.dart': "api.getAll('/api/symptoms/')",
      'lib/screens/adr_screen.dart': "api.getAll('/api/medications/')",
      'lib/screens/vital_events_screen.dart': "api.getAll('/api/diseases/')",
      'lib/screens/pharmacy_orders_screen.dart': "api.getAll('/api/pharmacy/suppliers/'",
      'lib/screens/pharmacy_stock_screen.dart': "api.getAll('/api/pharmacy/suppliers/'",
      'lib/screens/pharmacy_claims_screen.dart': "api.getAll('/api/pharmacy/hmos/'",
      'lib/screens/user_management_screen.dart': "api.getAll('/api/pharmacy/hmos/')",
      'lib/api.dart': "getAll('/api/tenants/prescribing/')",
    }.entries) {
      expect(src(entry.key), contains(entry.value), reason: entry.key);
    }
    // The screens that browse a resource page themselves; pulling every row
    // into them would be the slow path, not the safe one.
    expect(src('lib/screens/user_management_screen.dart'),
        contains("api.getList('/api/users/')"));
    expect(src('lib/screens/pharmacy_kit.dart'),
        contains('api.getList(widget.path, widget.query)'));
  });
}
