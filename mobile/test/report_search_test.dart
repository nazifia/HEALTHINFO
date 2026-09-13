import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/report_scaffold.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Typing in the list's search box must narrow the list to what the API
/// answered for that search, not leave the unfiltered rows on screen.
void main() {
  final rows = [
    {'id': 1, 'name': 'Musa Bello'},
    {'id': 2, 'name': 'Emeka Nwosu'},
    {'id': 3, 'name': 'Ada Obi'},
  ];

  MockClient server(List<Uri> seen) => MockClient((req) async {
    seen.add(req.url);
    final q = req.url.queryParameters['search']?.toLowerCase();
    final hits = q == null
        ? rows
        : rows.where((r) => r['name']!.toString().toLowerCase().contains(q));
    return http.Response(
      jsonEncode({'count': hits.length, 'results': hits.toList()}),
      200,
      headers: {'content-type': 'application/json'},
    );
  });

  testWidgets('search narrows the list to what the API answered', (
    tester,
  ) async {
    final seen = <Uri>[];
    await http.runWithClient(() async {
      await tester.pumpWidget(
        MaterialApp(
          home: ReportListScreen(
            path: '/api/x/',
            searchHint: 'Search',
            fabLabel: 'Add',
            showFab: false,
            emptyIcon: Icons.list,
            emptyTitle: 'None',
            emptyMessage: 'None',
            savedMessage: 'Saved',
            card: (row, reload, edit) => Text(row['name'] as String),
            form: (_) => const SizedBox(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Emeka Nwosu'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'musa');
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pumpAndSettle();

      expect(seen.last.queryParameters['search'], 'musa');
      expect(find.text('Musa Bello'), findsOneWidget);
      expect(find.text('Emeka Nwosu'), findsNothing);
    }, () => server(seen));
  });
}
