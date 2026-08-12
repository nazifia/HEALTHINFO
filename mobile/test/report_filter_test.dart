import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/report_scaffold.dart';

void main() {
  test('an unfiltered list asks for a bare URL', () {
    expect(listQuery('', {}), isNull);
    expect(listQuery('   ', {}), isNull);
  });

  test('search and filters travel together', () {
    expect(listQuery('Ada', {}), {'search': 'Ada'});
    expect(listQuery('', {'patient_type': 'nhia'}), {'patient_type': 'nhia'});
    expect(listQuery(' Ada ', {'patient_type': 'nhia', 'status': 'active'}), {
      'patient_type': 'nhia',
      'status': 'active',
      'search': 'Ada',
    });
  });

  test('a cleared filter is dropped from the request', () {
    final picked = <String, String>{'patient_type': 'nhia'};
    picked.remove('patient_type');
    expect(listQuery('', picked), isNull);
  });
}
