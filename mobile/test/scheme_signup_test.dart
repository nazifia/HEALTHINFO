import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/pharmacy.dart';

void main() {
  test('the scheme half rides nested; the admin half sits beside it', () {
    final body = schemeSignUpBody(
      tenantId: 7,
      name: '  AXA Mansard ',
      code: ' AXA ',
      coveragePercent: '80.00',
      preauthThreshold: '5000',
      autoSubmitClaims: true,
      adminPhone: ' 08031234567 ',
      adminName: ' Ada ',
      adminPassword: 's3curepass99',
    );
    expect(body['tenant'], 7);
    expect(body['scheme'], {
      'name': 'AXA Mansard',
      'code': 'AXA',
      'contact': '',
      'email': '',
      'coverage_percent': '80.00',
      'preauth_threshold': '5000',
      'auto_submit_claims': true,
    });
    expect(body['admin_phone'], '08031234567');
    expect(body['admin_name'], 'Ada');
    expect(body['admin_password'], 's3curepass99');
  });

  test('a threshold left blank is 0 — never ask first, not no cover', () {
    final body = schemeSignUpBody(
      tenantId: 1,
      name: 'Hygeia',
      coveragePercent: '  ',
      preauthThreshold: '   ',
      adminPhone: '08031234568',
      adminPassword: 's3curepass99',
    );
    final scheme = body['scheme'] as Map<String, dynamic>;
    expect(scheme['preauth_threshold'], '0');
    expect(scheme['coverage_percent'], '100');
  });

  test('a password is sent as typed — trimming one changes it', () {
    final body = schemeSignUpBody(
      tenantId: 1,
      name: 'Reliance',
      adminPhone: '08031234569',
      adminPassword: ' spaced pass 99 ',
    );
    expect(body['admin_password'], ' spaced pass 99 ');
  });

  Map<String, dynamic> ready({
    int? tenantId = 1,
    String name = 'Hygeia',
    String adminPhone = '08031234567',
    String adminPassword = 's3curepass99',
  }) =>
      schemeSignUpBody(
        tenantId: tenantId,
        name: name,
        adminPhone: adminPhone,
        adminPassword: adminPassword,
      );

  test('a body with both halves filled in is ready to send', () {
    expect(schemeSignUpProblem(ready()), isNull);
  });

  test('each half the API would refuse is named before the round trip', () {
    expect(schemeSignUpProblem(ready(tenantId: null)), contains('organization'));
    expect(schemeSignUpProblem(ready(name: '  ')), 'Name the scheme.');
    expect(schemeSignUpProblem(ready(adminPhone: ' ')), contains('phone number'));
    expect(
        schemeSignUpProblem(ready(adminPassword: 'short')), contains('8 characters'));
  });

  test('an insurer filed without a seat is only checked on the scheme half', () {
    final bare = ready(adminPhone: '', adminPassword: '');
    expect(schemeSignUpProblem(bare, withAdmin: false), isNull);
    expect(schemeSignUpProblem(bare), contains('phone number'));
    // The organization and the name still have to hold up: that row is a
    // scheme the counter prices sales off.
    expect(schemeSignUpProblem(ready(tenantId: null), withAdmin: false),
        contains('organization'));
  });
}
