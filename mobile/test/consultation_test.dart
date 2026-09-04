import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/consultations_screen.dart';

void main() {
  test('a follow-up date goes out as the API wants it', () {
    expect(consultationDate(DateTime(2026, 3, 7)), '2026-03-07');
    expect(consultationDate(DateTime(2026, 11, 30)), '2026-11-30');
  });

  test('no follow-up date is sent as null, not as today', () {
    expect(consultationDate(null), isNull);
  });
}
