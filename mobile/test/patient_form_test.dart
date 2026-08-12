import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/patients_screen.dart';

String? check({String type = 'regular', String nhis = ''}) => patientFormError(
      firstName: 'Ada',
      lastName: 'Obi',
      patientType: type,
      nhisNumber: nhis,
    );

void main() {
  test('a complete non-NHIA patient submits', () {
    expect(check(), isNull);
    expect(check(type: 'staff'), isNull);
  });

  test('names are required', () {
    expect(
      patientFormError(
          firstName: '  ', lastName: 'Obi', patientType: 'regular',
          nhisNumber: ''),
      isNotNull,
    );
  });

  test('NHIA needs an NHIS number', () {
    expect(check(type: 'nhia'), contains('NHIS'));
    expect(check(type: 'nhia', nhis: '   '), contains('NHIS'));
    expect(check(type: 'nhia', nhis: 'NHIS-1'), isNull);
  });

  test('type values match the ones the API accepts', () {
    expect(patientTypes.keys, contains('nhia'));
    expect(patientTypes.keys, contains('retainership'));
    expect(patientTypes['nhia'], 'NHIA');
  });
}
