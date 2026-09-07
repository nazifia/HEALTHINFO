import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/forgot_password_screen.dart';

void main() {
  test('reads uid and token out of the mailed link', () {
    expect(
      parseResetLink('https://health.example/#/reset?uid=Mg&token=abc-def'),
      {'uid': 'Mg', 'token': 'abc-def'},
    );
  });

  test('takes the query tail on its own, badly copied out of a mail app', () {
    expect(
      parseResetLink('  uid=Mg&token=abc-def  '),
      {'uid': 'Mg', 'token': 'abc-def'},
    );
  });

  test('anything without both halves is not a link', () {
    expect(parseResetLink(''), isNull);
    expect(parseResetLink('https://health.example/#/reset?uid=Mg'), isNull);
    expect(parseResetLink('what do I paste here'), isNull);
  });
}
