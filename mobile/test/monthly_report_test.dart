import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/pharmacy_reports_screen.dart';

final _now = DateTime(2026, 3, 14);

void main() {
  test('stepping back walks month by month, across a year boundary', () {
    expect(stepMonth(DateTime(2026, 3), -1, _now), DateTime(2026, 2));
    expect(stepMonth(DateTime(2026, 1), -1, _now), DateTime(2025, 12));
    expect(stepMonth(DateTime(2026, 1), -13, _now), DateTime(2024, 12));
  });

  test('stepping forward stops at the month we are in', () {
    expect(stepMonth(DateTime(2026, 2), 1, _now), DateTime(2026, 3));
    // Already on March: forward is refused, and the unchanged value is what
    // tells the screen not to refetch.
    expect(stepMonth(DateTime(2026, 3), 1, _now), DateTime(2026, 3));
    expect(stepMonth(DateTime(2025, 12), 12, _now), DateTime(2025, 12));
  });

  test('the day of the month never leaks into the result', () {
    expect(stepMonth(DateTime(2026, 2, 28), -1, DateTime(2026, 3, 31)),
        DateTime(2026, 1));
  });
}
