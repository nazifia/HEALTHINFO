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

  test('only patient logins are offered, plus the one already linked', () {
    final users = [
      {'id': 1, 'role': 'public', 'phone': '08031234567'},
      {'id': 2, 'role': 'doctor', 'phone': '08039999999'},
      {'id': 3, 'role': 'public', 'phone': '08037654321'},
    ];
    expect(linkableAccounts(users, null).map((u) => u['id']), [1, 3]);
    // A record already pointing at a staff account keeps that option, so
    // opening the form cannot silently drop the link.
    expect(linkableAccounts(users, 2).map((u) => u['id']), [1, 2, 3]);
  });

  test('an account reads as a person, falling back to the number', () {
    expect(accountLabel({'id': 1, 'username': 'Ada', 'phone': '08031234567'}),
        'Ada · 08031234567');
    expect(accountLabel({'id': 1, 'username': '', 'phone': '08031234567'}),
        '08031234567');
    expect(accountLabel({'id': 7}), 'Account #7');
  });

  test('type values match the ones the API accepts', () {
    expect(patientTypes.keys, contains('nhia'));
    expect(patientTypes.keys, contains('retainership'));
    expect(patientTypes['nhia'], 'NHIA');
  });
}
