import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/hmo_dashboard_screen.dart';

List<Map<String, dynamic>> schemes(Map<String, Object?> owed) =>
    [for (final e in owed.entries) {'name': e.key, 'outstanding': e.value}];

void main() {
  test('no period asked for is every claim, not a window of nothing', () {
    expect(hmoRange(null), isEmpty);
  });

  test('a picked period sends both ends as plain dates', () {
    final r = DateTimeRange(
        start: DateTime(2026, 1, 5), end: DateTime(2026, 2, 28, 23, 59));
    expect(hmoRange(r), {'from': '2026-01-05', 'to': '2026-02-28'});
  });

  test('schemes rank by what they still owe, not by what they were billed',
      () {
    final bars = owedByScheme(schemes({'Hygeia': '120.00', 'Reliance': '900.50'}));
    expect(bars.map((b) => b.label), ['Reliance', 'Hygeia']);
    expect(bars.first.value, 900.5);
  });

  test('a scheme that owes nothing still charts, at zero', () {
    final bars = owedByScheme(schemes({'Clearpay': '0.00', 'Late': null}));
    expect(bars.map((b) => b.value), [0, 0]);
    expect(bars.length, 2);
  });
}
