import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/stats_rows.dart';

void main() {
  test('an administrator reads every panel', () {
    for (final p in ['engagement', 'prescribing', 'adr', 'consultations']) {
      expect(readsPanel('tenant_admin', p), isTrue);
      expect(readsPanel('super_admin', p), isTrue);
    }
  });

  test('each profession reads the panels on its own work', () {
    expect(readsPanel('doctor', 'consultations'), isTrue);
    expect(readsPanel('doctor', 'engagement'), isFalse);
    expect(readsPanel('pharmacist', 'prescribing'), isTrue);
    expect(readsPanel('pharmacist', 'consultations'), isFalse);
    expect(readsPanel('midwife', 'adr'), isTrue);
    expect(readsPanel(null, 'adr'), isFalse);
    expect(readsPanel('doctor', 'no-such-panel'), isFalse);
  });
}
