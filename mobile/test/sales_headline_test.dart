import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/sales_headline.dart';

// Two states selling on the same day, an older day beside them, and money as
// the decimal strings the API actually sends.
final _payload = {
  'level': 'state',
  'daily': [
    {'state': 'Kano', 'period': '2026-09-09', 'revenue': '100.00', 'sales': 2},
    {'state': 'Kano', 'period': '2026-09-10', 'revenue': '250.50', 'sales': 3},
    {'state': 'Kwara', 'period': '2026-09-10', 'revenue': '49.50', 'sales': 1},
  ],
  'monthly': [
    {'state': 'Kano', 'period': '2026-08', 'revenue': '900.00', 'sales': 9},
    {'state': 'Kano', 'period': '2026-09', 'revenue': '350.50', 'sales': 5},
  ],
  'yearly': [
    {'state': 'Kano', 'period': '2026', 'revenue': '1250.50', 'sales': 14},
  ],
};

void main() {
  test('each bucket totals its latest period across every area', () {
    expect(salesHeadline(_payload), [
      (bucket: 'daily', period: '2026-09-10', revenue: 300.0, sales: 4),
      (bucket: 'monthly', period: '2026-09', revenue: 350.50, sales: 5),
      (bucket: 'yearly', period: '2026', revenue: 1250.50, sales: 14),
    ]);
  });

  test('an empty or missing bucket shows nothing, never a zero', () {
    expect(salesHeadline({'level': 'state', 'daily': [], 'monthly': []}), isEmpty);
    expect(salesHeadline(null), isEmpty);
    expect(salesByArea(null, 'monthly'), isEmpty);
  });

  test('the area rows are the latest period, named by the payload level', () {
    expect(salesByArea(_payload, 'daily'), [
      {'area': 'Kano', 'revenue': 250.50},
      {'area': 'Kwara', 'revenue': 49.50},
    ]);
  });

  test('a local-government seat is folded under its own level key', () {
    final local = {
      'level': 'local',
      'yearly': [
        {'local': 'Ilorin West', 'period': '2026', 'revenue': '10.00', 'sales': 1},
      ],
    };
    expect(salesByArea(local, 'yearly'), [
      {'area': 'Ilorin West', 'revenue': 10.0},
    ]);
  });
}
